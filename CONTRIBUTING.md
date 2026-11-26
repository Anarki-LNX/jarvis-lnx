# Contributing to NuOrb

Thanks for your interest! NuOrb is a small hobby project and every kind of help is welcome – you don't need to be a developer.

## Ways to help

- **Try it and report back.** Install it with the [install guide](INSTALL.md) and open an issue if something is unclear or breaks. "It didn't work on my Proxmox LXC because …" is exactly the kind of feedback we need.
- **Test on hardware we don't have.** vLLM on NVIDIA, LM Studio, Raspberry Pi 5, Synology, Unraid … – see the issues labelled [`help wanted`](https://github.com/Anarki-LNX/nuorb/labels/help%20wanted).
- **Android beta.** The NuOrb app is in closed testing on Google Play. Open an issue or comment on a post and we'll send you the invite.
- **Review code.** Security, Docker setup, shell scripts – fresh eyes are very welcome, especially from people who do this for a living.
- **Docs and translations.** The UI is German and English today. Other languages, clearer docs, better screenshots – all great first contributions.
- **Ideas.** Open an issue and describe what you'd like NuOrb to do.

New here? Look for issues labelled [`good first issue`](https://github.com/Anarki-LNX/nuorb/labels/good%20first%20issue).

## How to contribute code

1. Fork the repository and create a branch.
2. Keep changes small and focused; one topic per pull request.
3. Test what you changed. For the server: build the image and run the end-to-end test (see [`docker/README.md`](docker/README.md)).
4. Never commit secrets, API keys or real IP addresses/hostnames from your network. Use `192.168.1.50` as an example address.
5. Open a pull request and describe what you changed and how you tested it.

## Ground rules

- Be kind and constructive. Criticism of the code is welcome; attacks on people are not.
- Privacy first: NuOrb must keep working fully locally, without telemetry or accounts. Cloud features stay optional.
- Anything that switches devices or takes real-world actions must go through a confirmation card.

## How NuOrb is built

NuOrb is developed with heavy help from AI (Claude). The maintainer is not a professional programmer; ideas, decisions and testing come from the maintainer, most of the code is AI-generated. See [`AI_DECLARATION.md`](AI_DECLARATION.md) for details. That is exactly why reviews from experienced developers are so valuable.

## License

By contributing you agree that your contribution is released under the [MIT License](LICENSE).
