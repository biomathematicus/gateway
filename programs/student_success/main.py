"""Driver: regenerates every figure into code/figures/student_success.

Usage:  python main.py
Each figure module is also runnable on its own (python chord.py, etc.).
First run queries SQL Server and caches every result under data/pkl/;
subsequent runs are cache-only. Tunables live in config.py.
"""
import chord
import classsize
import heatmap


def main() -> None:
    chord.generate()        # figChord-MAT-top25, figChord-MAT-all
    classsize.generate()    # figClassSizeUTSA
    heatmap.generate()      # figHeatmapSubjectMajor-changers


if __name__ == "__main__":
    main()
