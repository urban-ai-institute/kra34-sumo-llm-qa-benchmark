This Overleaf template provides files for authors submitting to the ACM Hypertext Conference. It is based on the ACM Overleaf templates and add extra files to assist with styling references.

The template set comprises a number of files and folders.

main.tex
--------
This is the file in which your article is written. ACM has generic template TEX files for all possible submission types.  The 'main.tex. is based on this but most of the unneeded document content. See file 'sample-sigconf.pdf', especially Sections 5 through 8 for instructions on aspect like Keywords, Concepts and copyright boilerplate.

references.bib
--------------
A blank file to hold your BibTeX-format bibliography data.

sample-sigconf.pdf
------------------
A PDF, using the conference template, which explains aspects of a Conference paper's elements paper. To see the source TEX for the PDF see the 'Sample ACM TEX files folder'. If publishing for the first item to ACM, it is worth reading Sections 5 through 8 of this PDF

ACM Referencing Style Guide.pdf
-------------------------------
A guide on how best to prepare/configure BibTeX for use here. A description of the style types available to use and the BibTeX data needed by each type.  Ideally, your 'bib' file's data should generate zero LaTeX compilation log errors/warnings.

ACM 'acmart' LaTeX package files
--------------------------------
If unfamiliar with LaTeX, ignore these: they just ensure you are using more up-to-date ACM 'acmart' packages files than in a default Overleaf project (which uses packages from the TeX 2023 distribution). Files are 'ACM-Reference-Format.bst', 'acmart.cls', acmnumeric.bbx', 'acmnumeric.cbx'. These are copied from ACM 'acmart' package Version 2.08 (Overleaf default is v1.90. Do not delete or alter these files. they can be user updated by replacing with same-named files from a more recent 

FOLDER: Images
--------------
Place any images used in your article in here. The 'main.tex' article is set up (line #114) so you do not need to use the folder name, just use the image's file name as in most example code.

FOLDER: HT-References
---------------------
This contains 2 files.  A 'bib' file has ACM-correct references for every Hypertext Conference and conference article. These can be copied and used in your paper.  The PDF shows that data in a document rendered using the ACM's 'acmart' package.

~~~~~~~ OTHER MATERIAL ~~~~~~~~~~~~~
Items below here can be deleted if not wanted.

FOLDER: source files for sample-sigconf
----------------------------
This contains a subset of the overall ACM template set (most of which are inappropriate for most users). By selecting the 'sample-sigconf.tex' file in the folder, the Conference-format example source can be viewed. This may be useful for seeing how figures and tables are added. 'sample-sigconf.pdf' is the compiled version of the '.tex' file. The other files are support documents for compiling the '.tex' file.

CHANGE LOG
----------
2024-07-28 Added v2.08 'acmart' files to override Overleaf baseline default (March 2023) packages.

2024-03-24. Template project first created/submitted, to assist Overleaf-based submissions to the HT'24 Conference.