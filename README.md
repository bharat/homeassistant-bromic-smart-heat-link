# Bromic Smart Heat Link Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![Brand](https://github.com/bharat/homeassistant-bromic-smart-heat-link/actions/workflows/brand-validation.yml/badge.svg)](https://github.com/bharat/homeassistant-bromic-smart-heat-link/actions/workflows/brand-validation.yml)
[![Lint](https://github.com/bharat/homeassistant-bromic-smart-heat-link/actions/workflows/lint.yml/badge.svg)](https://github.com/bharat/homeassistant-bromic-smart-heat-link/actions/workflows/lint.yml)
[![Validate](https://github.com/bharat/homeassistant-bromic-smart-heat-link/actions/workflows/validate.yml/badge.svg)](https://github.com/bharat/homeassistant-bromic-smart-heat-link/actions/workflows/validate.yml)

A Home Assistant custom integration for controlling Bromic outdoor heaters via the Bromic Smart Heat Link device using RS232 serial communication.

## Features

- **Full Controller Support**: Works with both ON/OFF (4-button) and Dimmer (7-button) controllers
- **Multiple Controllers**: Support for up to 50 controller ID locations
- **Guided Learning Process**: Easy-to-follow wizard for pairing with your existing remote controls
- **Multiple Entity Types**:
  - Switches for ON/OFF controllers
  - Lights with brightness control for dimmer controllers
  - Buttons for dim up/down functions
  - Select entities for quick power level presets
- **Diagnostics**: Built-in diagnostics and error reporting
- **Services**: Developer services for testing and manual control

## Hardware Requirements

- Bromic Smart Heat Link device
- USB-to-RS232 adapter
- Compatible Bromic heater controllers (ON/OFF or Dimmer type)
- Existing paired remote controls for learning process

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots in the top right corner → "Custom repositories"
4. Add this repository URL and select "Integration" as the category
5. Install the integration and restart Home Assistant

### Manual Installation

1. Download the latest release
2. Copy the `custom_components/bromic_smart_heat_link` folder to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

### Initial Setup

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Bromic Smart Heat Link"
3. Select your USB-to-RS232 serial port from the discovered list
4. The integration will test the connection and complete setup

### Adding Controllers

After initial setup, you can add controllers through the integration options:

1. Go to **Settings** → **Devices & Services** → **Bromic Smart Heat Link** → **Configure**
2. Select **"Add New Controller"**
3. Choose an available ID location (1-50)
4. Select controller type:
   - **ON/OFF Controller**: 4 buttons (Ch1 ON/OFF, Ch2 ON/OFF)
   - **Dimmer Controller**: 7 buttons (100%, 75%, 50%, 25%, Dim Up, Dim Down, Off)

### Learning Process

For each controller, you'll go through a guided learning process:

1. **Press P3 on Remote**: Press and hold the P3 button on your existing remote
2. **Wait for Beep**: The controller will beep within 5 seconds
3. **Click Send Learn Command** as the tone begins. You may hear multiple short confirmation tones; that’s expected.
4. **Confirm**: Click "I heard the confirmation tones" to advance, or "Retry" if you didn’t hear them.
5. **Repeat** for each required button

The learning process teaches the Smart Heat Link to recognize commands that Home Assistant will send, without affecting your existing remote functionality.

## Entities Created

### ON/OFF Controllers
- `switch.bromic_id{X}_channel_1` - Channel 1 switch
- `switch.bromic_id{X}_channel_2` - Channel 2 switch

### Dimmer Controllers
- `light.bromic_id{X}_channel_1` - Channel 1 dimmable light
- `light.bromic_id{X}_channel_2` - Channel 2 dimmable light
- `select.bromic_id{X}_power_level` - Power level preset selector
- `button.bromic_id{X}_dim_up` - Dim up button (if learned)
- `button.bromic_id{X}_dim_down` - Dim down button (if learned)

## Protocol Details

The integration uses the Bromic Smart Heat Link RS232 protocol:

- **Baud Rate**: 19200
- **Data Bits**: 8
- **Parity**: None
- **Stop Bits**: 1
- **Flow Control**: None

Commands follow the format: `T + ID(2 bytes) + Button(2 bytes) + Checksum`

## Services

The integration provides several services for advanced users:

- `bromic_smart_heat_link.learn_button` - Learn a specific button
- `bromic_smart_heat_link.send_raw_command` - Send raw hex commands
- `bromic_smart_heat_link.clear_controller` - Clear controller (if supported)

## Troubleshooting

### Connection Issues
- Verify USB-to-RS232 adapter is connected
- Check serial port permissions (add HA user to `dialout` group on Linux)
- Use stable device paths like `/dev/serial/by-id/*` instead of `/dev/ttyUSB0`
- Refer to the [Bromic Smart Heat Link Installation Guide](docs/Bromic-Smart-Heat-Link-Installation-Guide.pdf)

### Learning Issues
- Ensure controller and remote are paired and working
- Press P3 and wait for beep before clicking "Learn Button"
- Stay within 30m RF range during learning
- Check for RF interference from other devices

### Entity Issues
- Entities only appear for successfully learned button combinations
- Restart Home Assistant after adding/removing controllers
- Check diagnostics page for detailed information

## Safety Notes

⚠️ **Important Safety Information**:
- Installation should be performed by a licensed electrician
- Keep low-voltage wiring separate from mains power
- Follow local electrical codes and regulations
- Ensure proper grounding and safety measures

## Support

- [GitHub Issues](https://github.com/bharat/homeassistant-bromic-smart-heat-link/issues)
- [Home Assistant Community Forum](https://community.home-assistant.io/)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This integration is not affiliated with Bromic Heating. Use at your own risk. Always follow proper safety procedures when working with electrical equipment.
