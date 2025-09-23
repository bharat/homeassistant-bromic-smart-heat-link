# Bromic Smart Heat Link Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![Brand](https://github.com/bharat/homeassistant-bromic-smart-heat-link/actions/workflows/brand-validation.yml/badge.svg)](https://github.com/bharat/homeassistant-bromic-smart-heat-link/actions/workflows/brand-validation.yml)
[![Lint](https://github.com/bharat/homeassistant-bromic-smart-heat-link/actions/workflows/lint.yml/badge.svg)](https://github.com/bharat/homeassistant-bromic-smart-heat-link/actions/workflows/lint.yml)
[![Validate](https://github.com/bharat/homeassistant-bromic-smart-heat-link/actions/workflows/validate.yml/badge.svg)](https://github.com/bharat/homeassistant-bromic-smart-heat-link/actions/workflows/validate.yml)
[![Release](https://img.shields.io/github/v/release/bharat/homeassistant-bromic-smart-heat-link?sort=semver)](https://github.com/bharat/homeassistant-bromic-smart-heat-link/releases)

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

There are a couple of ways setup may go depending on your system:

1. Go to **Settings** → **Devices & Services** → **Add Integration** and search for "Bromic Smart Heat Link".
2. Choose one of the following:
   - If your serial device is listed, select it and continue.
   - If it is not listed, choose **Other (enter manually)** and type the path (for example `/dev/serial/by-id/...` or `/dev/ttyUSB0`).
3. The integration will test the connection and complete setup.

Tip: On Linux you may need to ensure the Home Assistant user has permission to access serial devices (e.g., add the user to the `dialout` group, if necessary).

### Adding or Adopting Controllers

After initial setup, you can add controllers through the integration options:

1. Go to **Settings** → **Devices & Services** → **Bromic Smart Heat Link** → **Configure**
2. Select **Add New Controller** or **Adopt Existing Controller**
3. Choose an available ID location (1-50)
4. Select controller type:
   - **ON/OFF Controller**: 4 buttons (Ch1 ON/OFF, Ch2 ON/OFF)
   - **Dimmer Controller**: 7 buttons (100%, 75%, 50%, 25%, Dim Up, Dim Down, Off)

### Learning Process (when adding)

For each controller, you'll go through a guided learning process:

1. **Press P3 on Remote**: Press and hold the P3 button on your existing remote
2. **Wait for Beep**: The controller will beep within 5 seconds
3. **Click Send Learn Command** as the tone begins. You may hear multiple short confirmation tones; that’s expected.
4. **Confirm**: Click "I heard the confirmation tones" to advance, or "Retry" if you didn’t hear them.
5. **Repeat** for each required button

The learning process teaches the Smart Heat Link to recognize commands that Home Assistant will send, without affecting your existing remote functionality.

### Adopting an Existing Controller

If your Smart Heat Link is already programmed, use **Adopt Existing Controller** to assign it to an ID without re-learning. Select an unused ID location and the appropriate controller type; entities will be created immediately.

## Entities Created

Names no longer include a channel suffix; each controller is identified by its ID.

### ON/OFF Controllers
- `switch.bromic_id{X}` - Primary switch for the controller (Ch1 ON/OFF)

### Dimmer Controllers
- `light.bromic_id{X}` - Dimmable light entity
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
- Check serial port permissions (add HA user to `dialout` group on Linux, if necessary)
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

<!-- Safety notes omitted; SHL usage with this integration does not introduce special safety considerations beyond standard electrical practices. -->

## Support

- [GitHub Issues](https://github.com/bharat/homeassistant-bromic-smart-heat-link/issues)
- [Home Assistant Community Forum](https://community.home-assistant.io/)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This integration is not affiliated with Bromic Heating. Use at your own risk. Always follow proper safety procedures when working with electrical equipment.
