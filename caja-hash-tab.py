#!/usr/bin/python
#coding: utf-8

import locale, os
import hashlib
import threading
import re
import io
from os.path import basename

try:
    from urllib import unquote
except ImportError:
    from urllib.parse import unquote

from gi.repository import Caja, GObject, Gtk

# Locale foo
lang = locale.getdefaultlocale()[0]
locale_path = os.path.join(os.path.dirname(__file__), "caja-hash-tab/locale")
locale_file = os.path.join(locale_path, lang + ".csv")
if not os.path.isfile(locale_file):
    lang = lang.split("_")[0]
    locale_file = os.path.join(locale_path, lang + ".csv")

# GTK style sheet
GUI = """
<interface>
  <requires lib="gtk+" version="3.0"/>
  <object class="GtkScrolledWindow" id="mainWindow">
    <property name="visible">True</property>
    <property name="can_focus">True</property>
    <property name="hscrollbar_policy">never</property>
    <child>
      <object class="GtkViewport" id="viewport1">
        <property name="visible">True</property>
        <property name="can_focus">False</property>
        <child>
          <object class="GtkGrid" id="grid">
            <property name="visible">True</property>
            <property name="can_focus">False</property>
            <property name="vexpand">True</property>
            <property name="margin_left">8</property>
            <property name="margin_right">8</property>
            <property name="margin_top">8</property>
            <property name="margin_bottom">8</property>
            <property name="row_spacing">4</property>
            <property name="column_spacing">16</property>
          </object>
        </child>
      </object>
    </child>
  </object>
</interface>
"""

class HashTab(GObject.GObject, Caja.PropertyPageProvider):

    def get_property_pages(self, files):
        # Only one file supported
        if len(files) != 1:
            return

        # Skip if something other than a regular file is selected
        file = files[0]
        if file.get_uri_scheme() != 'file':
            return
        if file.is_directory():
            return

        # Get filename
        # TODO what about samba:// etc.?
        filepath = unquote(file.get_uri()[7:])
        filename = basename(filepath)
        # Apparently, there are still people out there who aren't using UTF-8
        try:
            filename = filename.decode("utf-8") # or maybe errors="ignore"
        except:
            pass # lol

        # Supported hash algorithms
        self.hash_dict = {}
        self.hash_dict["MD5"] = {"name": "md5", "len": 32}
        self.hash_dict["SHA1"] = {"name": "sha1", "len": 40}
        for a in hashlib.algorithms_guaranteed:
            k = a.upper()
            if k in self.hash_dict:
                continue
            if re.search(r'^sha\d', a):
                pass
            else:
                continue
            self.hash_dict[k] = {"name": a}

        # Tab caption
        self.property_label = Gtk.Label('Hash')
        self.property_label.show()

        # Init GTK layout
        self.builder = Gtk.Builder()
        self.builder.add_from_string(GUI)
        self.mainWindow = self.builder.get_object("mainWindow")
        grid = self.builder.get_object("grid")
        posx = 0
        # I wanted to use a VBox but it seems, that layout element
        # is being deprecated before I even get to use it.
        # https://people.gnome.org/~desrt/gtk/html/gtk-migrating-GtkGrid.html

        # Header
        label = Gtk.Label()
        label.set_markup("<b>#</b>")
        label.set_justify(Gtk.Justification.CENTER)
        label.show()
        grid.attach(label, 0, posx, 1, 1)
        label = Gtk.Label(filename)
        label.set_justify(Gtk.Justification.LEFT)
        label.show()
        grid.attach(label, 1, posx, 1, 1)
        posx += 1

        # Create buttons and textboxes for available hash algorithms
        for k, hash_data in self.hash_dict.items():
            hash_data["file"] = filepath
            hash_data["filename"] = filename
            # Button widget with name of hash algorithm
            button = Gtk.Button.new_with_label(k)
            button._key = k
            button.connect("clicked", self.start_calc)
            button.show()
            grid.attach(button, 0, posx, 1, 1)
            hash_data["button"] = button
            # Textbox with calculated hash value (or empty)
            textbox = Gtk.Entry()
            textbox.set_editable(False)
            textbox.set_hexpand(True)
            textbox.show()
            grid.attach(textbox, 1, posx, 1, 1)
            hash_data["textbox"] = textbox
            # ...
            posx += 1

        # MD5: self.start_calc(widget=None, key="MD5")

        # Separator
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.show()
        grid.attach(separator, 0, posx, 2, 1)
        posx += 1

        # Create textbox for user to paste hash for comparison
        # I wanted to put this into a second row of a VBox
        # to allow a different horizontal alignment but ... deprecated.
        label = Gtk.Label()
        label.set_justify(Gtk.Justification.RIGHT)
        self.compare_label = label
        label.show()
        grid.attach(label, 0, posx, 1, 1)
        textbox = Gtk.Entry()
        self.compare_textbox = textbox
        textbox.set_hexpand(True)
        textbox.show()
        self.compare_textbox = textbox
        textbox.connect("changed", self.check_compare)
        grid.attach(textbox, 1, posx, 1, 1)

        return Caja.PropertyPage(name="CajaPython::hash", label=self.property_label, page=self.mainWindow),

    def start_calc(self, widget, key=None):
        if key is None:
            key = widget._key
        hash_data = self.hash_dict[key]

        # Callback
        def cb_set_hash():
            hashsum = self.calc(key=key)
            hash_data["textbox"].set_text(hashsum)

        # Disable button, start calculating hash
        hash_data["button"].set_sensitive(False)
        thread = threading.Thread(target=cb_set_hash)
        thread.start()
        thread.join() # blocking

    def calc(self, key, file=None):
        hash_data = self.hash_dict[key]
        hashfunc = hash_data.get("hashfunc")
        if hashfunc is None:
            hashlib_name = hash_data["name"]
            hashfunc = hashlib.new(hashlib_name)
        if file is None:
            file = open(hash_data["file"], "rb")
        hashsum = calc_hash(hashfunc, file)
        if file is None:
            file.close()
        hash_data["hashsum"] = hashsum

        return hashsum

    def hash_len(self, key):
        f = io.BytesIO()
        hash_data = self.hash_dict[key]
        hashlib_name = hash_data["name"]
        hashfunc = hashlib.new(hashlib_name)
        hashsum = calc_hash(hashfunc=hashfunc, file=f)
        return len(hashsum)

    def check_compare(self, widget):
        textbox = self.compare_textbox
        compare_label = self.compare_label
        user_text = textbox.get_text()
        compare_label.set_text("")

        # Look for possible match
        for k, hash_data in self.hash_dict.items():
            if len(user_text) != self.hash_len(key=k):
                continue
            hashsum = hash_data.get("hashsum")
            if not hashsum:
                compare_label.set_text("%s? (not calculated)" % k)
            elif hashsum == user_text:
                compare_label.set_text("%s!" % k)
            # matching length but different hash -> no output

def calc_hash(hashfunc, file):
    for chunk in iter(lambda: file.read(4096), b""):
        hashfunc.update(chunk)
    hashsum = hashfunc.hexdigest()
    return hashsum

