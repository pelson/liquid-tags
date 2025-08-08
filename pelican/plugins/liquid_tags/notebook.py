"""
Notebook Tag
------------
This is a liquid-style tag to include a static html rendering of an IPython
notebook in a blog post.

Syntax
------
{% notebook filename.ipynb [ cells[start:end] language[language] ]%}

The file should be specified relative to the ``notebooks`` subdirectory of the
content directory.  Optionally, this subdirectory can be specified in the
config file:

    NOTEBOOK_DIR = 'notebooks'

The cells[start:end] statement is optional, and can be used to specify which
block of cells from the notebook to include.

The language statement is obvious and can be used to specify whether ipython2
or ipython3 syntax highlighting should be used.

Requirements
------------
- The plugin requires IPython version 1.0 or above.  It no longer supports the
  standalone nbconvert package, which has been deprecated.

Details
-------
Because the notebook relies on some rather extensive custom CSS, the use of
this plugin requires additional CSS to be inserted into the blog theme.
After typing "make html" when using the notebook tag, a file called
``_nb_header.html`` will be produced in the main directory.  The content
of the file should be included in the header of the theme.  An easy way
to accomplish this is to add the following lines within the header template
of the theme you use:

    {% if EXTRA_HEADER %}
      {{ EXTRA_HEADER }}
    {% endif %}

and in your ``pelicanconf.py`` file, include the line:

    EXTRA_HEADER = open('_nb_header.html').read().decode('utf-8')

this will insert the appropriate CSS.  All efforts have been made to ensure
that this CSS will not override formats within the blog theme, but there may
still be some conflicts.
"""

from copy import deepcopy
from functools import partial
import os
import re

from pygments.formatters import HtmlFormatter

from .mdx_liquid_tags import LiquidTags

import nbformat


from nbconvert.filters.highlight import _pygments_highlight

from nbconvert.exporters import HTMLExporter

from traitlets.config import Config

from nbconvert.preprocessors import Preprocessor



from traitlets import Integer

# ----------------------------------------------------------------------
# Some code that will be added to the header:
#  Some of the following javascript/css include is adapted from
#  IPython/nbconvert/templates/fullhtml.tpl, while some are custom tags
#  specifically designed to make the results look good within the
#  pelican-octopress theme.
JS_INCLUDE = r"""
<style type="text/css">
/* Overrides of notebook CSS for static HTML export */
div.entry-content {
  overflow: visible;
  padding: 8px;
}
.input_area {
  padding: 0.2em;
}

a.heading-anchor {
 white-space: normal;
}

.rendered_html
code {
 font-size: .8em;
}

pre.ipynb {
  color: black;
  background: #f7f7f7;
  border: none;
  box-shadow: none;
  margin-bottom: 0;
  padding: 0;
  margin: 0px;
  font-size: 13px;
}

/* remove the prompt div from text cells */
div.text_cell .prompt {
    display: none;
}

/* remove horizontal padding from text cells, */
/* so it aligns with outer body text */
div.text_cell_render {
    padding: 0.5em 0em;
}

img.anim_icon{padding:0; border:0; vertical-align:middle; -webkit-box-shadow:none; -box-shadow:none}

div.collapseheader {
    width=100%;
    background-color:#d3d3d3;
    padding: 2px;
    cursor: pointer;
    font-family:"Helvetica Neue",Helvetica,Arial,sans-serif;
}
</style>

<script type="text/x-mathjax-config">
MathJax.Hub.Config({
    tex2jax: {
        inlineMath: [['$','$'], ['\\(','\\)']],
        processEscapes: true,
        displayMath: [['$$','$$'], ["\\[","\\]"]]
    }
});
</script>
<script type="text/javascript" async src="https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.2/MathJax.js?config=TeX-MML-AM_CHTML">
</script>

<script src="https://ajax.googleapis.com/ajax/libs/jquery/1.10.2/jquery.min.js"></script>

<script type="text/javascript">
jQuery(document).ready(function($) {
    $("div.collapseheader").click(function () {
    $header = $(this).children("span").first();
    $codearea = $(this).children(".input_area");
    console.log($(this).children());
    $codearea.slideToggle(500, function () {
        $header.text(function () {
            return $codearea.is(":visible") ? "Collapse Code" : "Expand Code";
        });
    });
});
});
</script>

"""

CSS_WRAPPER = """
<style type="text/css">
{0}
</style>
"""


# ----------------------------------------------------------------------
# Create a custom preprocessor
class SliceIndex(Integer):
    """An integer trait that accepts None"""

    default_value = None

    def validate(self, obj, value):
        if value is None:
            return value
        else:
            return super().validate(obj, value)


class SubCell(Preprocessor):
    """A transformer to select a slice of the cells of a notebook"""

    start = SliceIndex(0, config=True, help="first cell of notebook to be converted")
    end = SliceIndex(None, config=True, help="last cell of notebook to be converted")

    def preprocess(self, nb, resources):
        nbc = deepcopy(nb)
        nbc.cells = nbc.cells[self.start : self.end]
        return nbc, resources



# ----------------------------------------------------------------------
# Custom highlighter:
#  instead of using class='highlight', use class='highlight-ipynb'
def custom_highlighter(source, language="ipython", metadata=None):
    formatter = HtmlFormatter(cssclass="highlight-ipynb")
    if not language:
        language = "ipython"
    output = _pygments_highlight(source, formatter, language)
    return output.replace("<pre>", '<pre class="ipynb">')


# ----------------------------------------------------------------------
# Below is the pelican plugin code.
#
SYNTAX = (
    "{% notebook /path/to/notebook.ipynb [ cells[start:end] ] [ language[language] ] %}"
)
FORMAT = re.compile(
    r"""^(\s+)?(?P<src>\S+)(\s+)?((cells\[)(?P<start>-?[0-9]*):(?P<end>-?[0-9]*)(\]))?(\s+)?((language\[)(?P<language>-?[a-z0-9\+\-]*)(\]))?(\s+)?$"""
)


@LiquidTags.register("notebook")
def notebook(preprocessor, tag, markup):
    match = FORMAT.search(markup)
    if match:
        argdict = match.groupdict()
        src = argdict["src"]
        start = argdict["start"]
        end = argdict["end"]
        language = argdict["language"]
    else:
        raise ValueError(
            "Error processing input, " "expected syntax: {}".format(SYNTAX)
        )

    if start:
        start = int(start)
    else:
        start = 0

    if end:
        end = int(end)
    else:
        end = None

    language_applied_highlighter = partial(custom_highlighter, language=language)

    nb_dir = preprocessor.configs.getConfig("NOTEBOOK_DIR")
    content_path = getattr(preprocessor.configs, 'PATH', 'content')
    nb_path = os.path.join(content_path, nb_dir, src)

    if not os.path.exists(nb_path):
        raise ValueError(f"File {nb_path} could not be found")

    notebook_output = preprocessor.configs.getConfig("NOTEBOOK_OUTPUT")
    if notebook_output is not False:
        output_prefix = os.path.join("content", notebook_output)
        # Note: This should be relative to the *target* fpath, but we don't
        # have that context within this extension. :(
        rel_output_prefix = os.path.relpath(output_prefix, os.path.dirname(nb_path))
        tmpl = (
            os.path.join(rel_output_prefix, os.path.splitext(src)[0])
            + "_{unique_key}_{cell_index}_{index}{extension}"
        )

        config_dict = {
            "CSSHTMLHeaderTransformer": {
                "enabled": True,
                "highlight_class": ".highlight-ipynb",
            },
            "SubCell": {"enabled": True, "start": start, "end": end},

            "ExtractOutputPreprocessor": {
                "enabled": True,
                "output_filename_template": tmpl,
            },
        }
    else:
        config_dict = {
            "CSSHTMLHeaderTransformer": {
                "enabled": True,
                "highlight_class": ".highlight-ipynb",
            },
            "SubCell": {"enabled": True, "start": start, "end": end},
            "ExtractOutputPreprocessor": {
                "enabled": False,
            }
        }

    # Create the custom notebook converter
    c = Config(config_dict)


    exporter = HTMLExporter(
        config=c,
        filters={"highlight2html": language_applied_highlighter},
        preprocessors=[SubCell],
    )

    # read and parse the notebook
    with open(nb_path, encoding="utf-8") as f:
        nb_text = f.read()
        nb_json = nbformat.reads(nb_text, as_version=4)

    (body, resources) = exporter.from_notebook_node(nb_json)
    for name, data in resources.get("outputs", {}).items():
        # We hardcode the output directory here... :(
        abs_name = name
        while abs_name.startswith("../"):
            abs_name = abs_name.replace("../", "", 1)
        full = os.path.join("output", abs_name)
        new_name = os.path.normpath(full)
        if not os.path.isdir(os.path.dirname(new_name)):
            os.makedirs(os.path.dirname(new_name))
        with open(new_name, "wb") as f:
            f.write(data)

    # if we haven't already saved the header, save it here.
    if not notebook.header_saved:

        # Filter out excessive CSS - only keep essential notebook CSS
        filtered_css = []
        for css_line in resources["inlining"]["css"]:
            # Skip modern JupyterLab theme CSS variables and excessive styling
            if ('var(--jp-' not in css_line and
                'pre { line-height:' not in css_line and
                'td.linenos' not in css_line and
                'span.linenos' not in css_line and
                '.highlight' not in css_line):
                filtered_css.append(css_line)

        # Only include filtered CSS if there's any, otherwise use our minimal CSS
        if filtered_css:
            header = "\n".join(CSS_WRAPPER.format(css_line) for css_line in filtered_css)
        else:
            header = ""
        header += JS_INCLUDE

        with open("_nb_header.html", "w") as f:
            f.write(header)
        notebook.header_saved = True

    # this will stash special characters so that they won't be transformed
    # by subsequent processes.
    body = preprocessor.configs.htmlStash.store(body)
    return body


notebook.header_saved = False


# ----------------------------------------------------------------------
# This import allows notebook to be a Pelican plugin
from .liquid_tags import register  # noqa
