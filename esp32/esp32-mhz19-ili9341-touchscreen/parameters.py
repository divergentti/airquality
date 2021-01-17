SSID1 = 'ap1'
PASSWORD1 = 'pw1'
SSID2 = 'ap2'
PASSWORD2 = 'pw2'
MQTT_PORT = '1883'
MQTT_USER = 'fillin'
MQTT_PASSWORD = 'fillin'
MQTT_SERVER = 'fillin'
WEBREPL_PASSWORD = "pwd"
CLIENT_ID = "ESP32-CO2-PARTICLE"
DHCP_NAME = "ESP32-CO2-PARTICLE"
TOPIC_ERRORS = 'virheet/koti/esp32'
NTPSERVER = 'pool.ntp.org'
#  Do not use UART0 (pins 3, 4) if you need REPL! Avoid UART2 16 & 17 pins too, they may cause spiram issues.
CO2_SENSOR_UART = 2
CO2_SENSOR_TX_PIN = 27
CO2_SENSOR_RX_PIN = 25
PARTICLE_SENSOR_UART = 1
PARTICLE_SENSOR_TX = 32
PARTICLE_SENSOR_RX = 33
# https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/spi_master.html
TFT_SPI = 1  # HSPI = ID1
TFT_DC_PIN = 4
TFT_CS_PIN = 15
TFT_MOSI_PIN = 13  # SDI
TFT_CLK_PIN = 14  # SCK
TFT_RST_PIN = 2
TFT_MISO_PIN = 12
TOUCHSCREEN_SPI = 2  # VSPI = ID2
TFT_TOUCH_SCLK_PIN = 18
TFT_TOUCH_MOSI_PIN = 23  # T_DIN
TFT_TOUCH_MISO_PIN = 19  # T_DO
TFT_TOUCH_CS_PIN = 5
TFT_TOUCH_IRQ_PIN = 0
I2C_SDA_PIN = 21
I2C_SCL_PIN = 22
