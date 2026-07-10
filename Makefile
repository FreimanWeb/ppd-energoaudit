# Цифровая модель энергоаудита ППД — команды разработки/верификации.
# Использование: make <цель>. Перед первым запуском: python -m venv .venv && pip install -e .

PY ?= python

.PHONY: help verify test app ingest

help:
	@echo "verify  — верификация ядра: модель↔xlsx по манифесту config/verification.yaml"
	@echo "test    — pytest (ядро, ingest, UI/AppTest)"
	@echo "app     — запустить дашборд (streamlit)"
	@echo "ingest  — нормализация телеметрии ДНС-7с"

verify:
	$(PY) -m ppd_audit.verify

test:
	$(PY) -m pytest -q

app:
	streamlit run app/main.py

ingest:
	$(PY) -m ppd_audit.ingest dns7s
