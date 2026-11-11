# Tricorder: common tasks. `make` lists them.
# Works with the GNU Make 3.81 that ships with macOS.
#
# Variables (set on the command line only, e.g. `make flash PORT=/dev/cu.usbmodem1101`):
#   PORT    Tab5 serial port; found by its USB serial number when unset
#   RUN     run directory under .local/runs (default: YYYYMMDD-<target>)
#   ENV     provisioning env file, e.g. .env.local.tricorder-ap
#   ARGS    extra arguments passed through to the underlying tool
#   PROVIDER  service model provider (default local: Ollama on the Mac)
#   DURATION  capture length in seconds (default 360)

SHELL := /bin/bash
.DEFAULT_GOAL := help

TOOLS     := .tools
IDF       := tools/idf.sh -C firmware
IDF_PY    := $(TOOLS)/python-env/bin/python
VENV      := $(TOOLS)/investigation-env
PY        := $(VENV)/bin/python
TODAY     := $(shell date +%Y%m%d)

# The Tab5's USB serial (README, Device notes). Listing ports does not open them.
TAB5_SERIAL := E8:F6:0A:E2:E0:0E
# Only command-line values count, so a PORT or ENV exported in your shell never leaks in.
ifneq ($(origin PORT),command line)
PORT = $(shell $(IDF_PY) -c 'from serial.tools.list_ports import comports; print(next((p.device for p in comports() if "$(TAB5_SERIAL)" in (p.hwid or "").upper()), ""))' 2>/dev/null)
endif
$(foreach v,ENV RUN ARGS PROVIDER DURATION,$(if $(filter command line,$(origin $(v))),,$(eval $(v) :=)))
PROVIDER := $(or $(PROVIDER),local)
DURATION := $(or $(DURATION),360)
# Mac sleep drops USB data mid-capture (README, Device notes).
CAFFEINATE := $(shell command -v caffeinate >/dev/null 2>&1 && echo caffeinate -is)

.PHONY: help bootstrap env env-speech test build flash ports service ops provision capture clean

help: ## List targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-z-]+:.*## / {printf "  \033[1m%-11s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo
	@echo "  Variables: PORT (auto-detected), RUN, ENV, ARGS, PROVIDER=$(PROVIDER), DURATION=$(DURATION)"

# --- Setup ---

bootstrap: ## Pinned vendor sources + ESP32-P4 toolchain (needs git, uv)
	python3 tools/bootstrap.py

$(IDF_PY):
	@echo "$(IDF_PY) is missing; run 'make bootstrap' first" >&2; exit 1

$(PY):
	python3 -m venv $(VENV)

$(VENV)/.base: $(PY) tools/investigation-requirements.txt tools/openai-requirements.txt
	$(PY) -m pip install -q -r tools/investigation-requirements.txt -r tools/openai-requirements.txt
	@touch $@

$(VENV)/.speech: $(VENV)/.base tools/stt-requirements.txt tools/tts-requirements.txt
	$(PY) -m pip install -q -r tools/stt-requirements.txt -r tools/tts-requirements.txt
	@touch $@

env: $(VENV)/.base ## Mac service + test environment
env-speech: $(VENV)/.speech ## Add local speech-to-text and Pocket TTS (Apple Silicon)

# --- Develop ---

test: env ## Host tests (C++ ones need `make bootstrap` for vendored cJSON)
	$(PY) -m unittest discover -s tests -q $(ARGS)

build: ## Build the firmware
	$(IDF) build

flash: ## Build and flash the Tab5 (finds it by its USB serial)
	@test -n "$(PORT)" || { echo "Tab5 ($(TAB5_SERIAL)) not found; run 'make ports' or pass PORT=..." >&2; exit 1; }
	$(IDF) -p $(PORT) flash

ports: $(IDF_PY) ## List serial ports; the Tab5 shows SER=E8:F6:0A:E2:E0:0E
	$(IDF_PY) -m serial.tools.list_ports -v

clean: ## Remove the firmware build directory
	rm -rf firmware/build

# --- Run ---

service: env-speech ## Mac service (PROVIDER=local; RUN, ARGS)
	$(PY) -m tools.service --output .local/runs/$(or $(RUN),$(TODAY)-service) --provider $(PROVIDER) $(ARGS)

ops: ## Bench operations TUI (needs uv)
	uv run tools/ops.py

provision: $(IDF_PY) ## Write Wi-Fi + service address over USB (ENV=.env.local.<name>; ARGS for --known/--endpoint)
	@test -n "$(ENV)" || { echo "Pass ENV=.env.local.<name>" >&2; exit 1; }
	@test -n "$(PORT)" || { echo "Tab5 ($(TAB5_SERIAL)) not found; run 'make ports' or pass PORT=..." >&2; exit 1; }
	$(IDF_PY) -m tools.provision_device --env $(ENV) --port $(PORT) --output .local/runs/$(or $(RUN),$(TODAY)-provision) $(ARGS)

capture: $(IDF_PY) ## Record serial telemetry with a reset (RUN, DURATION, ARGS)
	@test -n "$(PORT)" || { echo "Tab5 ($(TAB5_SERIAL)) not found; run 'make ports' or pass PORT=..." >&2; exit 1; }
	$(CAFFEINATE) $(IDF_PY) -m tools.capture_serial --port $(PORT) --output .local/runs/$(or $(RUN),$(TODAY)-capture) --seconds $(DURATION) --reset $(ARGS)
