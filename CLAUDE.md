# CLAUDE.md

## Notebook editing

The notebook cells in `lenny-analysis/lenny-analysis.ipynb` have no cell IDs. `NotebookEdit` insert without a cell_id places cells at position 0, not at the end. Use Python/JSON manipulation to insert or reorder cells at specific positions.
