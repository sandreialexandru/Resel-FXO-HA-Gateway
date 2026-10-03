#pragma once

#include <string>
#include <vector>

#include "esphome/core/component.h"
#include "esphome/components/speaker/speaker.h"

#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

namespace esphome {
namespace audio_tcp {

class AudioTcp : public Component {
 public:
  void set_port(uint16_t port) { this->port_ = port; }
  void set_token(const std::string &token) { this->token_ = token; }
  void set_speaker(speaker::Speaker *spk) { this->speaker_ = spk; }

  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::AFTER_WIFI; }

  /// Apelat din microphone.on_data (ruleaza in task-ul microfonului, NU in bucla principala).
  void push_mic(const uint8_t *data, size_t len);

  /// true = VORBESC: sunetul primit de la client merge la difuzor. false = il aruncam.
  void set_talk(bool talk);

  bool is_connected() const { return this->client_fd_ >= 0 && this->authed_; }

 protected:
  void close_client_(const char *why);
  void handle_rx_(const uint8_t *data, size_t len);
  void flush_to_speaker_();
  void flush_mic_();

  uint16_t port_{6054};
  std::string token_;
  speaker::Speaker *speaker_{nullptr};

  int listen_fd_{-1};
  volatile int client_fd_{-1};
  volatile bool authed_{false};
  bool talk_{false};
  std::string hello_;

  // client -> difuzor
  std::vector<uint8_t> rx_pending_;
  size_t rx_off_{0};

  // microfon -> client (protejat de mutex, scris din alt task)
  SemaphoreHandle_t mic_mutex_{nullptr};
  std::vector<uint8_t> mic_buf_;

  uint32_t mic_bytes_sent_{0};
  uint32_t spk_bytes_played_{0};
  uint32_t mic_bytes_dropped_{0};
  uint32_t last_stat_ms_{0};
};

}  // namespace audio_tcp
}  // namespace esphome
