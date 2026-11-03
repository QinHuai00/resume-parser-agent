.PHONY: install test eval eval-baseline serve lint clean

install:
	pip install -e ".[dev]"

test:
	pytest -q

dataset:
	python eval/make_dataset.py

eval: dataset
	python -m resume_agent.cli eval --provider mock --corrupt-rate 0.35 --max-repairs 1

eval-baseline: dataset
	python -m resume_agent.cli eval --provider mock --corrupt-rate 0.35 --max-repairs 0

serve:
	python -m resume_agent.cli serve --port 8000

clean:
	rm -rf out .pytest_cache **/__pycache__ *.egg-info