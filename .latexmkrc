# latexmk configuration for the sample paper.
#
# latexmk reads this file automatically when it runs in the repository root.
# Do not repeat these flags on the command line.
#
# SECURITY: this file is Perl and it runs with the permissions of whoever
# invokes latexmk. Treat changes to it as code changes, and never run
# latexmk on a checkout whose .latexmkrc you have not read.

$pdf_mode = 1;                      # pdflatex -> PDF
$out_dir = 'build';                 # keep artifacts out of the source tree
$aux_dir = 'build';                 # .aux/.bbl/.log alongside the PDF

$pdflatex = 'pdflatex -synctex=1 -file-line-error -interaction=nonstopmode -halt-on-error %O %S';
$bibtex_use = 2;                    # run bibtex when .bib files change
$bibtex = 'bibtex %O %S';

$max_repeat = 5;                    # enough passes for refs + citations
$clean_ext = 'synctex.gz run.xml bbl blg fdb_latexmk fls';

# Keep the console log readable in CI: print errors, not the full transcript.
$silent = 0;
$print_type = 'p';

# No shell-escape, no previewer, no automatic PDF viewer launch.
$pdf_previewer = '';
$pdf_update_method = 0;
