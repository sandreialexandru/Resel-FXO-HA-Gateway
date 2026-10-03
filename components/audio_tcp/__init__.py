"""audio_tcp: server TCP simplu pentru sunet PCM (16 kHz, 16 biti, mono) intre ESP si un client din LAN.

Protocol (un singur client o data):
  1. clientul trimite o linie ASCII:  "AUDIO1 <token>\\n"  (token gol daca nu ai setat `token:`)
  2. ESP -> client: PCM brut de la microfon (doar cat timp microfonul e pornit = ASCULT)
  3. client -> ESP: PCM brut pentru difuzor (acceptat doar cat PTT = VORBESC, altfel e ignorat)
"""
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import speaker
from esphome.const import CONF_ID, CONF_PORT

DEPENDENCIES = ["network"]
CODEOWNERS = []

audio_tcp_ns = cg.esphome_ns.namespace("audio_tcp")
AudioTcp = audio_tcp_ns.class_("AudioTcp", cg.Component)

CONF_TOKEN = "token"
CONF_SPEAKER = "speaker"

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(AudioTcp),
        cv.Optional(CONF_PORT, default=6054): cv.port,
        cv.Optional(CONF_TOKEN, default=""): cv.string,
        cv.Optional(CONF_SPEAKER): cv.use_id(speaker.Speaker),
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_port(config[CONF_PORT]))
    cg.add(var.set_token(config[CONF_TOKEN]))
    if CONF_SPEAKER in config:
        spk = await cg.get_variable(config[CONF_SPEAKER])
        cg.add(var.set_speaker(spk))
