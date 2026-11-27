# Installing NuOrb

**▶ Prefer video?** Watch the 3-minute install tutorial: https://youtu.be/NO66dwKtCvg

[Deutsch](INSTALL.de.md)

NuOrb is a private voice assistant you run yourself: **one Docker container** on a home server, a Proxmox VM/LXC or
your PC. Your phone (NuOrb app) or any browser in your home network talks to it.

## 1. Requirements

| | Minimum |
|---|---|
| Machine | Linux, amd64 or arm64, 4 CPU cores, 4 GB free RAM, 8 GB disk |
| Software | Docker with Compose v2 (the installer tells you the exact command if it is missing) |
| Internet | once, for the image (~1.2 GB) and the speech models (~530 MB) |
| Brain | an [Ollama](https://ollama.com) server or any OpenAI-compatible server (llama.cpp, vLLM, LM Studio) **or** an [Anthropic API key](https://console.anthropic.com) (Claude), or both |
| Network | phone and server in the same home network, or connected by VPN (WireGuard, Tailscale) |

Proxmox LXC: enable nesting and keyctl first. On the Proxmox host: `pct set <ID> -features nesting=1,keyctl=1`.

## 2. One-command install

```bash
curl -fsSL https://raw.githubusercontent.com/Anarki-LNX/nuorb/main/install.sh | bash
```

Works from any shell (also fish/zsh, the script runs in bash). German: append `-s -- --lang de`.

The installer:

1. checks curl, Docker, Docker Compose, your Docker permissions and Docker's network settings and prints the exact fix
   for your distribution (Debian/Ubuntu, Fedora, Arch/CachyOS, openSUSE, Alpine);
2. asks only what it cannot detect: language, this server's IP address (detected, Enter confirms), Ollama (detected
   if it runs on this machine);
3. checks the firewall (ufw/firewalld) and shows the rules needed for the home network. It runs them **only if you
   say yes** and never opens anything to the internet;
4. downloads and starts NuOrb, waits until it is ready and then shows **the admin address and the setup code**.

Options: `--dir DIR` (default `~/nuorb`), `--ports 8443,8444`, `--lang de|en`, `--ip 192.168.1.50`,
`--ollama http://192.168.1.50:11434|none`, `--yes` (no questions; never runs sudo), `--no-firewall`, `--uninstall`.
Example: `curl -fsSL …/install.sh | bash -s -- --lang en --ports 9443,9444`.

Running the same command again **updates or repairs** the installation. Your settings and data stay.

## 3. First steps

1. Open `https://<server-ip>:8444` (e.g. `https://192.168.1.50:8444`). The browser warns about the certificate:
   expected, NuOrb creates its own. Continue.
2. Enter the **setup code** shown by the installer, choose a password.
3. Follow the setup: name, language, voice, **brain** (Ollama and/or Claude).
4. **Pair your phone:** admin panel → *Pair device* → scan the QR code with the NuOrb app. The code is valid for
   10 minutes and only once. A browser can be paired the same way (`https://<server-ip>:8443`).

Forgot the setup code? `docker compose -f ~/nuorb/compose.yaml logs nuorb | grep -i "setup code"`
(only shown until a password is set).

## 4. Brain

### Ollama (local, free, nothing leaves your home)

On the computer running Ollama:

- let it listen on the network: `sudo systemctl edit ollama` → add
  ```
  [Service]
  Environment="OLLAMA_HOST=0.0.0.0"
  Environment="OLLAMA_CONTEXT_LENGTH=65536"
  ```
  then `sudo systemctl restart ollama`. **NuOrb needs at least 64k context.**
- firewall on that computer: allow port 11434 from your home network only, e.g. `sudo ufw allow from 192.168.1.0/24 to any port 11434 proto tcp`.
  If Ollama runs **on the same machine** as NuOrb, also allow Docker: `sudo ufw allow from 172.16.0.0/12 to any port 11434 proto tcp`.
- in the setup, enter the **IP address** of that computer, e.g. `http://192.168.1.50:11434`, also when it is the
  same machine. Names like `pc.local` often do not resolve inside the container.
- good models: ones with tool use, e.g. Gemma, Qwen, Llama 3.x (8B+).

### llama.cpp, vLLM, LM Studio instead of Ollama

NuOrb works with **any server that speaks the OpenAI chat API**. In the setup choose
**“OpenAI-compatible”**, enter the address (with port, without `/v1`) and, if the server needs one, the API key.
The installer detects such servers on the same machine (ports 8080, 8000, 1234) on its own.

Requirements for every server: **tool calling** must work, **context ≥ 64k (65536)**, it must **listen on the network**
(not only 127.0.0.1), and its port must be open in the firewall of that computer (from Docker: `172.16.0.0/12`).

**llama.cpp** (`llama-server`, port 8080):
```bash
llama-server -m Qwen3-8B-Q4_K_M.gguf --alias qwen3-8b --host 0.0.0.0 --port 8080 -c 65536 -ngl 99 --jinja \
  -ctk q8_0 -ctv q8_0 --api-key YOUR_KEY        # --api-key is optional
```
- `--alias` gives the model a short name (otherwise it is called like the file path).
- Model with a native 32k window (e.g. Qwen3 ≤ 32B): add `--rope-scaling yarn --rope-scale 2 --yarn-orig-ctx 32768`.
- Context does not fit into VRAM: keep `-ctk q8_0 -ctv q8_0` (half the KV cache) or use a smaller model.
- Tested: Qwen3-4B Q4_K_M with 64k context: knowledge questions, clock and notes via tools work.

**vLLM** (port 8000):
```bash
vllm serve Qwen/Qwen3-8B --host 0.0.0.0 --port 8000 --max-model-len 65536 \
  --enable-auto-tool-choice --tool-call-parser hermes
```
- Tool parser per model family: Qwen2.5/3 → `hermes`, Llama 3.1+ → `llama3_json`, Mistral → `mistral`, gpt-oss → `openai`.
- Without `--enable-auto-tool-choice` vLLM rejects requests with tools (HTTP 400) and NuOrb does not answer.
- Model with a native 32k window (e.g. Qwen2.5): stretch it with YaRN:
  `--hf-overrides '{"rope_parameters":{"rope_type":"yarn","factor":2.0,"original_max_position_embeddings":32768,"rope_theta":1000000.0},"max_position_embeddings":65536}'`
  (`rope_theta` from the model's `config.json`; without it vLLM 0.34 fails at start).
- Optional `--api-key YOUR_KEY`; NuOrb then reports a missing or wrong key in the connection test.
- Without an NVIDIA GPU there is the official CPU image `vllm/vllm-openai-cpu` (slow, only for small models): add
  `--shm-size 512m` to `docker run` and `-e VLLM_CPU_KVCACHE_SPACE=2` (GB for the context).
- Tested: vLLM 0.34.0 (CPU image) with Qwen2.5-0.5B-Instruct and 64k context (YaRN): detection, version,
  context, API key errors, tool calls and the confirmation card work. The 0.5B model itself answers poorly;
  for everyday use take 8B or larger on a GPU.

**LM Studio** (port 1234): Developer tab → start the server, switch on *Serve on Local Network*. When loading the
model set **Context Length ≥ 65536** (the default is often 4096). Headless (`llmster`, installer from lmstudio.ai):
```bash
lms daemon up
lms server start --port 1234 --bind 0.0.0.0
lms load qwen3-4b-instruct-2507 --context-length 65536 --gpu max --identifier qwen3-4b
```
- **Load the model before NuOrb asks.** A model LM Studio loads on demand gets the default context and already the
  first question fails (“conversation has grown too long”). The connection test shows the loaded context and warns
  when no model is loaded or the context is below 64k.
- Embedding models from LM Studio are not offered as brain.
- API tokens: switch on *Require Authentication* in the app (Developer → Server Settings) and enter the token in NuOrb.
  `lms` (llmster 0.1.2) has no option for it. Without it LM Studio accepts any key.
- Tested: LM Studio llmster 0.1.2 (llama.cpp Vulkan runtime 2.83.0) with Qwen3-4B-Instruct-2507 Q4_K_M and 64k context:
  knowledge questions, clock via tool and the confirmation card work.

**LocalAI** (port 8080): in the model YAML set `context_size: 65536` and enable the function template.

Not every server is tested equally: llama.cpp, Ollama, vLLM (CPU image) and LM Studio were tested with NuOrb;
LocalAI follows its documentation. Existing Ollama installations keep working unchanged.

### Claude (no own GPU needed, costs per question)

Create a key at [console.anthropic.com](https://console.anthropic.com), enter it in the setup. Set a spending limit
there. A short voice question costs about 0.1-0.5 cents with Haiku. Conversation text goes to Anthropic (USA); audio
always stays local. *Both (automatic)* uses Ollama and falls back to Claude when the PC is off.

## 5. Firewall and ports

| Port | What | Who needs it |
|---|---|---|
| 8443 | app/UI | phones and browsers in your home network |
| 8444 | admin panel | your browser in the home network |

Never forward these ports on your router. When away, use a VPN into your home network.

**ufw** (Ubuntu, CachyOS, Arch …):
```bash
sudo ufw default allow routed                                             # containers may reach the internet
sudo ufw allow from 192.168.1.0/24 to any port 8443,8444 proto tcp        # your home network only
sudo ufw reload
```
**firewalld** (Fedora, openSUSE):
```bash
sudo firewall-cmd --permanent --add-rich-rule='rule family=ipv4 source address=192.168.1.0/24 port port=8443 protocol=tcp accept'
sudo firewall-cmd --permanent --add-rich-rule='rule family=ipv4 source address=192.168.1.0/24 port port=8444 protocol=tcp accept'
sudo firewall-cmd --reload
```
Replace `192.168.1.0/24` with your home network.

## 6. Manual installation (alternative)

```bash
mkdir -p ~/nuorb && cd ~/nuorb
curl -fsSLO https://raw.githubusercontent.com/Anarki-LNX/nuorb/main/docker/compose.yaml
curl -fsSL  https://raw.githubusercontent.com/Anarki-LNX/nuorb/main/docker/.env.example -o .env
nano .env                       # at least NUORB_HOSTS=192.168.1.50 (this server's IP), NUORB_LANG, TZ
docker compose up -d
docker compose logs -f nuorb    # wait for "setup code", Ctrl+C
```
The settings names start with `NUORB_` for historical reasons; they are explained in `.env`.

## 7. Update, backup, uninstall

- **Update:** run the install command again, or `cd ~/nuorb && docker compose pull && docker compose up -d`.
- **Backup:** `docker run --rm -v nuorb_data:/d -v "$PWD":/b debian tar czf /b/nuorb-data.tgz -C /d .`
- **Uninstall:** `curl -fsSL …/install.sh | bash -s -- --uninstall`: asks before removing; data is only deleted
  after typing `DELETE`.
- **From v0.3.x or older** (container `nuorb-nuorb-1`): just run the install command, it finds the old
  installation, takes over its settings and keeps the data. Manually: `docker compose -p nuorb down`
  (**without** `-v`), then the new `compose.yaml` and `docker compose up -d`.

## 8. Troubleshooting

| Problem | Cause and fix |
|---|---|
| `curl … \| bash` in fish shows an error | Use exactly the command above; fish passes the script to bash. Other commands from this guide: run `bash` first. |
| `permission denied … docker.sock` | `sudo usermod -aG docker $USER`, log out and in again (or use sudo). |
| Setup code not in the log yet | NuOrb is still starting (first start ~1-2 min). Wait, or: `docker compose exec nuorb cat /opt/data/nuorb/admin/setup-code.txt`. |
| Setup: *“The container has no internet connection”*, speech models stuck | Host firewall drops container traffic: ufw `sudo ufw default allow routed && sudo ufw reload`; firewalld: `sudo firewall-cmd --permanent --zone=trusted --add-interface=docker0 && sudo firewall-cmd --reload`. |
| Containers have no network at all | `/etc/docker/daemon.json` contains `"iptables": false` or `"bridge": "none"`. Remove both, `sudo systemctl restart docker`. |
| `unable to derive the IP value for host-gateway` | Your Docker has no default bridge; do not use `host.docker.internal`, use the machine's IP. |
| Ollama *not reachable* / ConnectTimeout | Ollama listens only on 127.0.0.1 → `OLLAMA_HOST=0.0.0.0`; firewall on the Ollama machine → allow 11434 (from Docker `172.16.0.0/12` if it is the same machine); use the IP, not `.local`. The setup shows the exact firewall commands for that computer. |
| *context window … below 64,000* | Context too small → Ollama `OLLAMA_CONTEXT_LENGTH=65536`, llama.cpp `-c 65536`, vLLM `--max-model-len 65536`, LM Studio Context Length 65536; restart the server. |
| llama.cpp/vLLM/LM Studio *not reachable* (Timeout) | The server listens only on 127.0.0.1 → `--host 0.0.0.0` / *Serve on Local Network*; open its port in the PC firewall (`sudo ufw allow from 172.16.0.0/12 to any port 8080 proto tcp`). |
| *The server requires an API key* | The server was started with `--api-key` → enter the same key in the setup. |
| vLLM: NuOrb does not answer, server log shows HTTP 400 | Start vLLM with `--enable-auto-tool-choice --tool-call-parser …`. |
| Browser: *connection not private* | Expected with NuOrb's own certificate: continue, or import `https://<server-ip>:8443/nuorb-ca.crt`. |
| App: certificate error after changing the IP | The IP is missing in `NUORB_HOSTS` in `~/nuorb/.env` → add it, `docker compose up -d`, pair again. |
| Phone cannot connect | Same network/VPN? Firewall rule for 8443 (see 5)? Address in the app = `https://<server-ip>:8443`. |
| *Port 8443 is already in use* | Install with other ports: `… \| bash -s -- --ports 9443,9444`. |
| Old version still running (port conflict after update) | `docker compose -p nuorb down` (without `-v`), then run the installer again. |
| Proxmox LXC: Docker does not start | On the host: `pct set <ID> -features nesting=1,keyctl=1`, restart the LXC. |
| Smart home does not switch | See [docker/README.md](docker/README.md#smart-home-optional): works reliably with Claude; with a local model switch off the tool search. |

More details: [docker/README.md](docker/README.md).
