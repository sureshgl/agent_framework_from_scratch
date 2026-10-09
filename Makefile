.PHONY: test evals demo

test:
	pytest -q

evals:
	python -m evals.run

demo:
	python -m examples.reconciliation