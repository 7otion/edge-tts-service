# Edge TTS Service

A minimal Python wrapper service for Microsoft Edge TTS (Text-to-Speech), designed to run as a background process and communicate via stdin/stdout using JSON messages.

## Features
- Simple command-based interface (speak, cancel, get_voices, shutdown)
- Streams synthesized audio as PCM via stdout
- Uses [edge-tts](https://github.com/rany2/edge-tts) for speech synthesis
- Cross-platform (Windows/Linux)

## Requirements
- Python 3+
- [edge-tts](https://pypi.org/project/edge-tts/)

## Usage
1. Install dependencies:
   ```sh
   pip install edge-tts
   ```
2. Run the service:
   ```sh
   python edge_tts_service.py
   ```
3. Communicate with the service using JSON lines via stdin/stdout.

## Example Commands
- Speak text:
  ```json
  {"cmd": "speak", "text": "Hello world!", "voice": "en-US-AriaNeural"}
  ```
- Cancel current speech:
  ```json
  {"cmd": "cancel"}
  ```
- Get available voices:
  ```json
  {"cmd": "get_voices"}
  ```
- Shutdown service:
  ```json
  {"cmd": "shutdown"}
  ```

## Notes
- Audio is streamed as raw PCM with a small header for each chunk.
- Status and error messages are sent to stderr as JSON lines.
- This project is intended as a simple backend utility and not a full-featured TTS application.

## License
MIT
