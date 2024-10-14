#! /usr/bin/env python3
#######################################################################################################################
#  Copyright (c) 2021 Nikolai Shkurkin (nshkurkin [at] ftlgoats [dot] com)
#  License: MIT
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to deal
#  in the Software without restriction, including without limitation the rights
#  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#  copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
# 
#  The above copyright notice and this permission notice shall be included in all
#  copies or substantial portions of the Software.
# 
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#  SOFTWARE.
#
#######################################################################################################################
# About this fork made 2024-10-10
# Author: Bengt Ragnemalm
# Changes: This fork is a fix according to Issue #1. It's broken functionality since InkScape 1.2
# The fix included the replacement of code according to the suggested fix PLUS replacement of the Image Magick command
# "convert" that in recent versions has been changed to "magick convert".
# Note that the plugin requires install if Image Magick. (Hint: Beware when downloading Image Magick, there are a lot
# of problematic ads on the project page. Make sure to only click on true download links).
#
# Use: Nothing changed.
# Tip for quick use: If you already has a file with cards consisting of one layer per card and one or more common
# background layers the described method is is an easy way to with minimal effort add typical functionality.
# (Much more advanced combinations can be made). The command will export each card as an individual JPEG to a folder.
# 1. Create a new layer that will act as a common top layer.
# 2. Move all card layers as sublayers to the common top layer.
# 2. To the new Top layer, using XML editor, add attribute with Name=export-layer-combos and Value=front,combo-children
# "front" can be any word. Note: No space between , and combo-children
# 3. For convenience, put all common background layers in another layer.
# 4. To use, hide all card layers and show all background layers that you want included onm the cards.
# 5. Run the command (Extensions -> Export -> Export Layer Combos).
#
# Since you already have Image Magick you can if you want, use a command to pack the output files into sets of 2x4 to a
# A4 page as JPEG files or one pdf.
# Run the command from a command prompt
# pdf output: magick montage *.jpg -rotate 90 -tile 2x3 -geometry +0+0 -page A4 output.pdf
# JPEG output: magick montage *.jpg -rotate 90 -tile 2x3 -geometry +0+0 -resize 2480x3508 output.jpg
# It's possible to add this functionality as options directly into the plugin but I wanted to change as little as
# possible.
#######################################################################################################################
#
# NOTES
#
# Developing extensions:
#   SEE: https://inkscape.org/develop/extensions/
#   SEE: https://wiki.inkscape.org/wiki/Python_modules_for_extensions
#   SEE: https://wiki.inkscape.org/wiki/Using_the_Command_Line
#
# Implementation References:
#   SEE: https://github.com/jespino/inkscape-export-layers/blob/master/export_layers.py
#   SEE: https://inkscape-extensions-guide.readthedocs.io/en/latest/_modules/inkex/base.html#InkscapeExtension.effect

import sys
sys.path.append('/usr/share/inkscape/extensions')
import inkex
import os
import subprocess
import tempfile
import shutil
import copy
from lxml import etree
import logging

#######################################################################################################################


class ExportSpec(object):
    """A description of how to export a layer."""

    ATTR_ID = "export-layer-combo"
    SELECTORS = ["combo-children", "visible", "hidden"]

    def __init__(self, spec: str, layer: object, group: str, selector: str):
        self.layer = layer
        self.spec = spec
        self.group = group
        self.selector = selector

    @staticmethod
    def create_specs(layer) -> list:
        """Extracts '[group],[selector]' pairs from the layer's ATTR_ID attribute and returns them as a 
           list of ExportSpec. A RuntimeError is raised if any are incorrectly formatted. 
        """
        result = list()
        if ExportSpec.ATTR_ID not in layer.source.attrib:
            return result
        
        spec = layer.source.attrib[ExportSpec.ATTR_ID]
        for group_selector in spec.split(";"):
            gs_split = group_selector.split(",")
            if len(gs_split) != 2:
                raise RuntimeError(f"layer '{layer.label}'(#{layer.id}) has an invalid form '{gs_split}'. " +
                                   f"Expected format is '[group],[selector]'")

            group = gs_split[0]
            selector = gs_split[1]
            if selector not in ExportSpec.SELECTORS:
                raise RuntimeError(f"layer '{layer.label}'(#{layer.id}) has an invalid selector '{selector}'. " +
                                   f"Only the following are valid: {str(ExportSpec.SELECTORS)}")

            result.append(ExportSpec(spec, layer, group, selector))

        return result

class CustomNamedTemporaryFile: 
    """
    MODIFIED FROM : https://stackoverflow.com/questions/23212435/permission-denied-to-write-to-my-temporary-file
    This custom implementation is needed because of the following limitation of tempfile.NamedTemporaryFile:

    > Whether the name can be used to open the file a second time, while the named temporary file is still open,
    > varies across platforms (it can be so used on Unix; it cannot on Windows NT or later).
    """
    def __init__(self, mode='wb', suffix="", delete=True):
        self._mode = mode
        self._delete = delete
        self.suffix = suffix

    def __enter__(self):
        # Generate a random temporary file name
        file_name = os.path.join(tempfile.gettempdir(), os.urandom(24).hex())+self.suffix
        # Ensure the file is created
        open(file_name, "x").close()
        # Open the file in the given mode
        self._tempFile = open(file_name, self._mode)
        return self._tempFile

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._tempFile.close()
        if self._delete:
            os.remove(self._tempFile.name)

class LayerRef(object):
    """A wrapper around an Inkscape XML layer object plus some helper data for doing combination exports."""

    def __init__(self, source: etree.Element):
        self.source = source
        self.id = source.attrib["id"]
        label_attrib_name = LayerRef.get_layer_attrib_name(source)
        self.label = source.attrib[label_attrib_name]
        self.children = list()
        self.parent = None

        self.export_specs = list()
        self.request_hidden_state = False
        self.requested_hidden = False
        self.sibling_ids = list()

        self.export_specs = ExportSpec.create_specs(self)

    @staticmethod
    def get_layer_attrib_name(layer: etree.Element) -> str:
        return "{%s}label" % layer.nsmap['inkscape']
    
    def has_valid_export_spec(self):
        return len(self.export_specs) > 0

    def copy_with_hidden(self, is_hidden: bool, hide_siblings: bool = False):
        result = LayerRef(self.source)
        result.request_hidden_state = True
        result.requested_hidden = is_hidden
        result.requested_hide_siblings = hide_siblings
        if self.parent is not None:
            for layer in self.parent.children:
                if layer.id != result.id:
                    result.sibling_ids.append(layer.id)
        return result


def recurse_combine(combo_items: list, idx: int = 0) -> list:
    """Recursively expands 'combo_items' into a list of permutations.
    
        For example recurse_combine([[A, B, C], [D, E], [F]]) returns

        [[A, D, F], [A, E, F], [B, D, F], [B, E, F], [C, D, F], [C, E, F]]
    
    """
    result = []
    if idx < len(combo_items):
        recurse_result = recurse_combine(combo_items, idx + 1)
        for item in combo_items[idx]:
            for sub_item in recurse_result:
                sub_result = [item]
                sub_result.extend(sub_item)
                result.append(sub_result)
            if len(recurse_result) == 0:
                result.append([item])
    return result


class ComboExport(inkex.Effect):
    """The core logic of exporting combinations of layers as images."""

    def __init__(self):
        super().__init__()
        self.arg_parser.add_argument("--path", type=str, dest="path", default="~/", help="The directory to export into")
        self.arg_parser.add_argument('-f', '--filetype', type=str, dest='filetype', default='jpeg', 
                                     help='Exported file type. One of [png|jpeg]')
        self.arg_parser.add_argument("--dpi", type=float, dest="dpi", default=90.0, help="DPI of exported image")
        self.arg_parser.add_argument("--ascii", type=inkex.Boolean, dest="ascii", default=False, 
                                     help="If true, removes non-ascii characters from layer names during export")
        self.arg_parser.add_argument("--negatives", type=inkex.Boolean, dest="negatives", default=False, 
                                     help="If true, allows the names of forced hidden layers to be a part of file names")
        self.arg_parser.add_argument("--lower", type=inkex.Boolean, dest="lower", default=False, 
                                     help="If true, foces the final file name to be lowercase")
        self.arg_parser.add_argument("--debug", type=inkex.Boolean, dest="debug", default=False, help="Print debug messages as warnings")
        self.arg_parser.add_argument("--one", type=inkex.Boolean, dest="one", default=False, help='Stop after processing one combination')
        self.arg_parser.add_argument("--dry", type=inkex.Boolean, dest="dry", default=False, help="Don't actually do all of the exports")

    def effect(self):
        logit = logging.warning if self.options.debug else logging.info

        logit(f"Options: {str(self.options)}")

        layers = self.get_layers()
        groups = dict()

        # Figure out the groups of permutations.
        for layer in layers:
            if not layer.has_valid_export_spec():
                continue
            
            logit(f"Found valid layer '{layer.label}' with '{len(layer.export_specs)}' exports, it has {len(layer.children)} children.")
            for export in layer.export_specs:
                if export.group not in groups:
                    groups[export.group] = list()
                groups[export.group].append(export)

        # Now generate each permutation.
        for group in groups:
            combo_list = groups[group]

            # Expand the list.
            expanded_list = list()
            for export in combo_list:
                # Add all children with hidden to set False, but with hidden siblings.
                if export.selector == "combo-children":
                    child_list = list()
                    for child in export.layer.children:
                        child_list.append(child.copy_with_hidden(False, hide_siblings=True))
                    expanded_list.append(child_list)
                # Add list with single item, but with hidden state set correctly.
                elif export.selector in ["visible", "hidden"]:
                    expanded_list.append([export.layer.copy_with_hidden(export.selector == "hidden")])
            
            # Create the permutations
            combos = recurse_combine(expanded_list)
            logit(f"Computed {len(combos)} combos:")
            for combo in combos:
                contents = ""
                show = list()
                hide = list()
                # Figure out what to show and what to hide.
                for item in combo:
                    if item.requested_hidden:
                        hide.append(item.id)
                    else:
                        show.append(item.id)
                        # Also show all parent layers as well.
                        parent = item.parent
                        while parent is not None:
                            show.append(parent.id)
                            parent = parent.parent
                        # If requested, hide siblings.
                        if item.requested_hide_siblings:
                            hide.extend(item.sibling_ids)

                    if item.requested_hidden and not self.options.negatives:
                        continue
                    contents += f"-{'no-' if item.requested_hidden else ''}{item.label.replace(' ', '')}"
            
                label = f"{group}{contents}"
                if self.options.ascii:
                    label = label.encode("ascii", "ignore").decode()
                if self.options.lower:
                    label = label.lower()

                logit(f"  {label}")

                if self.options.dry:
                    logit(f"Skipping because --dry was specified")
                    continue

                # Actually do the export into the destination path.
                output_path = os.path.expanduser(self.options.path)
                if not os.path.exists(os.path.join(output_path)):
                    logit(f"Creating directory path {output_path} because it does not exist")
                    os.makedirs(os.path.join(output_path))

                # If OS is Windows, use a the CustomNamedTemporaryFile.
                if os.name == "nt":
                    with CustomNamedTemporaryFile(suffix=".svg") as fp_svg:
                        layer_dest_svg_path = fp_svg.name
                        logit(f"Writing SVG to temporary location {layer_dest_svg_path}")
                        self.export_layers(layer_dest_svg_path, show, hide)

                        if self.options.filetype == "jpeg":
                            with CustomNamedTemporaryFile(suffix=".png") as fp_png:
                                logit(f"Writing PNG to temporary location {fp_png.name}")
                                self.export_to_png(layer_dest_svg_path, fp_png.name)
                                layer_dest_jpg_path = os.path.join(output_path, f"{label}.jpg")
                                logit(f"Writing JPEG to final location {layer_dest_jpg_path}")
                                self.convert_png_to_jpeg(fp_png.name, layer_dest_jpg_path)
                        else:
                            layer_dest_png_path = os.path.join(output_path, f"{label}.png")
                            logit(f"Writing PNG to final location {layer_dest_png_path}")
                            self.export_to_png(layer_dest_svg_path, layer_dest_png_path)
                else : # Otherwise, use the standard NamedTemporaryFile.
                    with tempfile.NamedTemporaryFile(suffix=".svg") as fp_svg:
                        layer_dest_svg_path = fp_svg.name
                        logit(f"Writing SVG to temporary location {layer_dest_svg_path}")
                        self.export_layers(layer_dest_svg_path, show, hide)

                        if self.options.filetype == "jpeg":
                            with tempfile.NamedTemporaryFile(suffix=".png") as fp_png:
                                logit(f"Writing PNG to temporary location {fp_png.name}")
                                self.export_to_png(layer_dest_svg_path, fp_png.name)
                                layer_dest_jpg_path = os.path.join(output_path, f"{label}.jpg")
                                logit(f"Writing JPEG to final location {layer_dest_jpg_path}")
                                self.convert_png_to_jpeg(fp_png.name, layer_dest_jpg_path)
                        else:
                            layer_dest_png_path = os.path.join(output_path, f"{label}.png")
                            logit(f"Writing PNG to final location {layer_dest_png_path}")
                            self.export_to_png(layer_dest_svg_path, layer_dest_png_path)


#                with tempfile.NamedTemporaryFile(suffix=".svg") as fp_svg:
#                    layer_dest_svg_path = fp_svg.name
#                    logit(f"Writing SVG to temporary location {layer_dest_svg_path}")
#                    self.export_layers(layer_dest_svg_path, show, hide)
#
#                    if self.options.filetype == "jpeg":
#                        with tempfile.NamedTemporaryFile(suffix=".png") as fp_png:
#                            logit(f"Writing PNG to temporary location {fp_png.name}")
#                            self.export_to_png(layer_dest_svg_path, fp_png.name)
#                            layer_dest_jpg_path = os.path.join(output_path, f"{label}.jpg")
#                            logit(f"Writing JPEG to final location {layer_dest_jpg_path}")
#                            self.convert_png_to_jpeg(fp_png.name, layer_dest_jpg_path)
#                    else:
#                        layer_dest_png_path = os.path.join(output_path, f"{label}.png")
#                        logit(f"Writing PNG to final location {layer_dest_png_path}")
#                        self.export_to_png(layer_dest_svg_path, layer_dest_png_path)
#                
                # Break on first output for debug purposes
                if self.options.one:
                    break
            
            # Break on first output for debug purposes
            if self.options.one:
                    break

        
    def get_layers(self) -> list:
        svg_layers = self.document.xpath('//svg:g[@inkscape:groupmode="layer"]', namespaces=inkex.NSS)
        layers = []

        # Find all of our "valid" layers.
        for layer in svg_layers:
            label_attrib_name = LayerRef.get_layer_attrib_name(layer)
            if label_attrib_name not in layer.attrib:
                continue
            layers.append(LayerRef(layer))

        # Create the layer hierarchy (children and parents).
        for layer in layers:
            for other in layers:
                for child in layer.source.getchildren():
                    if child is other.source:
                        layer.children.append(other)
                if layer.source.getparent() is other.source:
                    layer.parent = other 

        return layers

    def export_layers(self, dest: str, show: list, hide: list):
        logit = logging.warning if self.options.debug else logging.info
        doc = copy.deepcopy(self.document)
        for layer in doc.xpath('//svg:g[@inkscape:groupmode="layer"]', namespaces=inkex.NSS):
            id = layer.attrib["id"]
            label_attrib_name = LayerRef.get_layer_attrib_name(layer)
            label = layer.attrib[label_attrib_name]

            if id in show:
                layer.attrib['style'] = 'display:inline'
                logit(f" ... showing layer '{label}'")
            if id in hide:
                layer.attrib['style'] = 'display:none'
                logit(f" ... hiding layer '{label}'")
        doc.write(dest)

    def export_to_png(self, svg_path: str, output_path: str):
        logit = logging.warning if self.options.debug else logging.info
        command = f"inkscape --export-type=\"png\" -d {self.options.dpi} --export-filename=\"{output_path}\" \"{svg_path}\""
        logit(f"Running command '{command}'")
       
#        p = subprocess.Popen(command.encode("utf-8"), shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p.wait()
        output, err = p.communicate()
        logit(f"stdout:\n{output}")
        logit(f"stderr:\n{err}")

    def convert_png_to_jpeg(self, png_path: str, output_path: str):
        logit = logging.warning if self.options.debug else logging.info
        command = f"magick convert \"{png_path}\" \"{output_path}\""
        logit(f"Running command '{command}'")

#        p = subprocess.Popen(command.encode("utf-8"), shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p.wait()
        output, err = p.communicate()
        logit(f"stdout:\n{output}")
        logit(f"stderr:\n{err}")

#######################################################################################################################

def _main():
    effect = ComboExport()
    effect.run()
    exit()

if __name__ == "__main__":
    _main()

#######################################################################################################################
