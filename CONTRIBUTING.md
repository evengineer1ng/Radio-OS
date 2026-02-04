# Contributing to Radio OS

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

1. Clone and create a virtual environment:
```bash
git clone https://github.com/yourusername/radio_os.git
cd radio_os
python -m venv radioenv
source radioenv/bin/activate
pip install -r requirements.txt
```

2. Create a feature branch:
```bash
git checkout -b feature/my-feature
```

## Code Style

- Use 4 spaces for indentation
- Follow PEP 8 where reasonable
- Add docstrings to functions and classes
- Keep lines under 100 characters where practical

## Areas for Contribution

### Feed Plugins
Create new plugins in `plugins/` to add content sources:
- News aggregators
- Social media integration
- Custom APIs
- Data feeds

See existing plugins for structure.

### Media Control
Add platform support beyond Windows/macOS:
- Linux (MPRIS2, D-Bus)
- Other streaming services

### TTS & Voices
- Integration with additional TTS engines (gTTS, ElevenLabs, etc.)
- More voice models
- Real-time voice synthesis improvements

### Documentation
- Usage guides
- Plugin development tutorials
- API documentation

### Bug Fixes
Test thoroughly on multiple platforms before submitting PRs.

## Submitting Changes

1. Ensure your code doesn't break existing functionality
2. Test on Windows, macOS, or Linux as applicable
3. Create a clear commit message explaining your changes
4. Push to your fork and submit a pull request
5. Respond to code review feedback

## Questions?

Open an issue for discussion or email the maintainers.
