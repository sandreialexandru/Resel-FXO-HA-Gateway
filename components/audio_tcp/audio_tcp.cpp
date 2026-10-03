#include "audio_tcp.h"

#include <cerrno>
#include <cstring>

#include "esphome/core/hal.h"
#include "esphome/core/log.h"

#include "lwip/sockets.h"

namespace esphome {
namespace audio_tcp {

static const char *const TAG = "audio_tcp";

// Limite de memorie (placa nu are PSRAM): ~0.5 s de sunet la 16 kHz / 16 biti / mono = 16000 octeti.
static const size_t MIC_BUF_MAX = 8000;      // 250 ms
static const size_t RX_PENDING_MAX = 16000;  // 500 ms
static const size_t HELLO_MAX = 96;

void AudioTcp::setup() {
  this->mic_mutex_ = xSemaphoreCreateMutex();
  this->mic_buf_.reserve(MIC_BUF_MAX);
  this->rx_pending_.reserve(2048);

  this->listen_fd_ = lwip_socket(AF_INET, SOCK_STREAM, 0);
  if (this->listen_fd_ < 0) {
    ESP_LOGE(TAG, "socket() a esuat (errno %d)", errno);
    this->mark_failed();
    return;
  }
  int yes = 1;
  lwip_setsockopt(this->listen_fd_, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));

  struct sockaddr_in addr;
  memset(&addr, 0, sizeof(addr));
  addr.sin_family = AF_INET;
  addr.sin_addr.s_addr = htonl(INADDR_ANY);
  addr.sin_port = htons(this->port_);
  if (lwip_bind(this->listen_fd_, (struct sockaddr *) &addr, sizeof(addr)) != 0) {
    ESP_LOGE(TAG, "bind() pe portul %u a esuat (errno %d)", this->port_, errno);
    this->mark_failed();
    return;
  }
  if (lwip_listen(this->listen_fd_, 1) != 0) {
    ESP_LOGE(TAG, "listen() a esuat (errno %d)", errno);
    this->mark_failed();
    return;
  }
  int fl = lwip_fcntl(this->listen_fd_, F_GETFL, 0);
  lwip_fcntl(this->listen_fd_, F_SETFL, fl | O_NONBLOCK);
}

void AudioTcp::dump_config() {
  ESP_LOGCONFIG(TAG, "Audio TCP:");
  ESP_LOGCONFIG(TAG, "  Port: %u", this->port_);
  ESP_LOGCONFIG(TAG, "  Token: %s", this->token_.empty() ? "(niciunul)" : "(setat)");
  ESP_LOGCONFIG(TAG, "  Speaker: %s", this->speaker_ != nullptr ? "da" : "nu");
}

void AudioTcp::close_client_(const char *why) {
  if (this->client_fd_ >= 0) {
    ESP_LOGI(TAG, "Client deconectat (%s)", why);
    lwip_close(this->client_fd_);
  }
  this->client_fd_ = -1;
  this->authed_ = false;
  this->hello_.clear();
  this->rx_pending_.clear();
  this->rx_off_ = 0;
  if (this->mic_mutex_ != nullptr && xSemaphoreTake(this->mic_mutex_, pdMS_TO_TICKS(20)) == pdTRUE) {
    this->mic_buf_.clear();
    xSemaphoreGive(this->mic_mutex_);
  }
}

void AudioTcp::push_mic(const uint8_t *data, size_t len) {
  if (!this->is_connected() || this->mic_mutex_ == nullptr || len == 0)
    return;
  if (xSemaphoreTake(this->mic_mutex_, pdMS_TO_TICKS(5)) != pdTRUE) {
    this->mic_bytes_dropped_ += len;
    return;
  }
  if (this->mic_buf_.size() + len > MIC_BUF_MAX) {
    // clientul nu tine pasul: aruncam datele noi (ramanem aproape de timp real)
    this->mic_bytes_dropped_ += len;
  } else {
    this->mic_buf_.insert(this->mic_buf_.end(), data, data + len);
  }
  xSemaphoreGive(this->mic_mutex_);
}

void AudioTcp::set_talk(bool talk) {
  if (this->talk_ == talk)
    return;
  this->talk_ = talk;
  this->rx_pending_.clear();
  this->rx_off_ = 0;
  if (this->speaker_ == nullptr)
    return;
  if (talk) {
    this->speaker_->start();
  } else {
    this->speaker_->finish();  // reda ce a ramas in buffer, apoi se opreste
  }
  ESP_LOGI(TAG, "Difuzor: %s", talk ? "pornit (VORBESC)" : "oprit");
}

void AudioTcp::handle_rx_(const uint8_t *data, size_t len) {
  if (!this->authed_) {
    size_t i = 0;
    while (i < len && this->hello_.size() <= HELLO_MAX) {
      char c = (char) data[i++];
      if (c == '\n') {
        std::string expected = this->token_.empty() ? std::string("AUDIO1") : "AUDIO1 " + this->token_;
        std::string got = this->hello_;
        if (!got.empty() && got.back() == '\r')
          got.pop_back();
        if (got == expected) {
          this->authed_ = true;
          ESP_LOGI(TAG, "Client autentificat");
          // ce a mai ramas dupa linie e deja audio
          if (i < len)
            this->handle_rx_(data + i, len - i);
        } else {
          this->close_client_("token gresit");
        }
        return;
      }
      this->hello_.push_back(c);
    }
    if (this->hello_.size() > HELLO_MAX)
      this->close_client_("salut prea lung");
    return;
  }
  if (!this->talk_ || this->speaker_ == nullptr)
    return;  // nu vorbim: aruncam
  if (this->rx_pending_.size() + len > RX_PENDING_MAX)
    return;  // difuzorul nu tine pasul: aruncam
  this->rx_pending_.insert(this->rx_pending_.end(), data, data + len);
}

void AudioTcp::flush_to_speaker_() {
  if (!this->talk_ || this->speaker_ == nullptr)
    return;
  while (this->rx_off_ < this->rx_pending_.size()) {
    size_t w = this->speaker_->play(this->rx_pending_.data() + this->rx_off_, this->rx_pending_.size() - this->rx_off_);
    if (w == 0)
      break;
    this->rx_off_ += w;
    this->spk_bytes_played_ += w;
  }
  if (this->rx_off_ >= this->rx_pending_.size()) {
    this->rx_pending_.clear();
    this->rx_off_ = 0;
  }
}

void AudioTcp::flush_mic_() {
  if (this->mic_mutex_ == nullptr || !this->is_connected())
    return;
  std::vector<uint8_t> local;
  if (xSemaphoreTake(this->mic_mutex_, 0) != pdTRUE)
    return;
  local.swap(this->mic_buf_);
  xSemaphoreGive(this->mic_mutex_);
  size_t off = 0;
  while (off < local.size()) {
    int n = lwip_send(this->client_fd_, local.data() + off, local.size() - off, MSG_DONTWAIT);
    if (n > 0) {
      off += n;
      this->mic_bytes_sent_ += n;
    } else if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
      this->mic_bytes_dropped_ += local.size() - off;  // reteaua nu tine pasul
      break;
    } else {
      this->close_client_("eroare la trimitere");
      break;
    }
  }
}

void AudioTcp::loop() {
  if (this->listen_fd_ < 0)
    return;

  // client nou? il preferam pe cel nou (daca s-a pierdut conexiunea veche, nu o stim inca)
  int fd = lwip_accept(this->listen_fd_, nullptr, nullptr);
  if (fd >= 0) {
    if (this->client_fd_ >= 0)
      this->close_client_("inlocuit de un client nou");
    int fl = lwip_fcntl(fd, F_GETFL, 0);
    lwip_fcntl(fd, F_SETFL, fl | O_NONBLOCK);
    int one = 1;
    lwip_setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));
    this->client_fd_ = fd;
    this->authed_ = false;  // intotdeauna cerem linia de salut
    this->hello_.clear();
    ESP_LOGI(TAG, "Client conectat, astept salutul");
  }

  if (this->client_fd_ >= 0) {
    uint8_t buf[512];
    for (int i = 0; i < 4 && this->client_fd_ >= 0; i++) {
      int n = lwip_recv(this->client_fd_, buf, sizeof(buf), MSG_DONTWAIT);
      if (n > 0) {
        this->handle_rx_(buf, n);
      } else if (n == 0) {
        this->close_client_("inchis de client");
      } else {
        if (errno != EAGAIN && errno != EWOULDBLOCK)
          this->close_client_("eroare la citire");
        break;
      }
    }
    this->flush_to_speaker_();
    this->flush_mic_();
  }

  uint32_t now = millis();
  if (this->client_fd_ >= 0 && now - this->last_stat_ms_ > 5000) {
    this->last_stat_ms_ = now;
    ESP_LOGD(TAG, "mic trimis: %u B, aruncat: %u B, difuzor: %u B", (unsigned) this->mic_bytes_sent_,
             (unsigned) this->mic_bytes_dropped_, (unsigned) this->spk_bytes_played_);
  }
}

}  // namespace audio_tcp
}  // namespace esphome
