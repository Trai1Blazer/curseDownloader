#!/usr/bin/python
# -*- coding: utf-8 -*-
import appdirs
import argparse
import json
import os
import requests
import shutil
from urllib.parse import urlparse, unquote
from pathlib import Path
from threading import Thread
from tkinter import ttk, filedialog, sys, Tk, N, S, E, W, StringVar, Text, Scrollbar, END


compiledExecutable = False
# If in frozen state(aka executable) then use this path, else use original path.
if getattr(sys, 'frozen', False):
    # if frozen, get embedded file
    CA_Certificates = os.path.join(os.path.dirname(sys.executable), 'cacert.pem')
    compiledExecutable = True
else:
    # else just get the default file
    CA_Certificates = requests.certs.where()
# https://stackoverflow.com/questions/15157502/requests-library-missing-file-after-cx-freeze
os.environ["REQUESTS_CA_BUNDLE"] = CA_Certificates


parser = argparse.ArgumentParser(description="Download Curse modpack mods")
parser.add_argument("--manifest", help="manifest.json file from unzipped pack")
parser.add_argument("--nogui", dest="gui", action="store_false", help="Do not use gui to to select manifest")
parser.add_argument("--portable", dest="portable", action="store_true", help="Use portable cache")
args, unknown = parser.parse_known_args()


# Simplify output text for both console and GUI.
def print_text(message):
    message == str(message)
    print(message)
    if args.gui:
        programGui.set_output(message)


class DownloadUI(ttk.Frame):
    def __init__(self):
        self.root = Tk()
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.parent = ttk.Frame(self.root)
        self.parent.grid(column=0, row=0, sticky=(N, S, E, W))
        self.parent.columnconfigure(0, weight=1)
        self.parent.rowconfigure(0, weight=1)
        ttk.Frame.__init__(self, self.parent, padding=(6, 6, 14, 14))
        self.grid(column=0, row=0, sticky=(N, S, E, W))
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self.root.title("Curse Pack Downloader")

        self.manifestPath = StringVar()

        chooser_container = ttk.Frame(self)
        self.chooserText = ttk.Label(chooser_container, text="Locate 'manifest.json': ")
        chooser_entry = ttk.Entry(chooser_container, textvariable=self.manifestPath)
        self.chooserButton = ttk.Button(chooser_container, text="Browse", command=self.choose_file)
        self.chooserText.grid(column=0, row=0, sticky=W)
        chooser_entry.grid(column=1, row=0, sticky=(E, W), padx=5)
        self.chooserButton.grid(column=2, row=0, sticky=E)
        chooser_container.grid(column=0, row=0, sticky=(E, W))
        chooser_container.columnconfigure(1, weight=1)
        self.downloadButton = ttk.Button(self, text="Download mods", command=self.go_download)
        self.downloadButton.grid(column=0, row=1, sticky=(E, W))

        self.logText = Text(self, state="disabled", wrap="none")
        self.logText.grid(column=0, row=2, sticky=(N, E, S, W))

        self.logScroll = Scrollbar(self, command=self.logText.yview)
        self.logScroll.grid(column=1, row=2, sticky=(N, E, S, W))
        self.logText['yscrollcommand'] = self.logScroll.set

    def choose_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=(("Json files", "*.json"),),
            initialdir=os.path.expanduser("~"),
            parent=self)
        self.manifestPath.set(file_path)

    def go_download(self):
        t = Thread(target=self.go_download_background)
        t.start()

    def go_download_background(self):
        self.downloadButton.configure(state="disabled")
        self.chooserButton.configure(state="disabled")
        do_download(self.manifestPath.get())
        self.downloadButton.configure(state="enabled")
        self.chooserButton.configure(state="enabled")

    def set_output(self, message):
        self.logText["state"] = "normal"
        self.logText.insert("end", message + "\n")
        self.logText.see(END)
        self.logText["state"] = "disabled"

    def set_manifest(self, file_name):
        self.manifestPath.set(file_name)


class HeadlessUI:
    def set_output(self, message):
        pass


programGui = None


def do_download(manifest):
    if manifest == '':
        print_text("Select a manifest file first!")
        return None
    manifest_path = Path(manifest)
    target_dir_path = manifest_path.parent

    manifest_text = manifest_path.open().read()
    manifest_text = manifest_text.replace('\r', '').replace('\n', '')

    manifest_json = json.loads(manifest_text)

    try:
        if not "minecraftModpack" == manifest_json['manifestType']:
            print_text('Manifest Error. manifestType is not "minecraftModpack"')
            return None
    except KeyError as e:
        print_text('I got a KeyError - reason %s' % str(e))
        print_text("Manifest Error. Make sure you selected a valid pack manifest.json")
        return None

    try:
        override_path = Path(target_dir_path, manifest_json['overrides'])
        minecraft_path = Path(target_dir_path, "minecraft")
        mods_path = minecraft_path / "mods"
    except KeyError as e:
        print_text('I got a KeyError - reason %s' % str(e))
        print_text("Manifest Error. Make sure you selected a valid pack manifest.json")
        return None

    if override_path.exists():
        shutil.move(str(override_path), str(minecraft_path))

    downloader_dirs = appdirs.AppDirs(appname="cursePackDownloader", appauthor="portablejim")
    cache_path = Path(downloader_dirs.user_cache_dir, "curseCache")

    # Attempt to set proper portable data directory if asked for
    if args.portable:
        if getattr(sys, 'frozen', False):
            # if frozen, get embeded file
            cache_path = Path(os.path.join(os.path.dirname(sys.executable), 'curseCache'))
        else:
            if '__file__' in globals():
                cache_path = Path(os.path.dirname(os.path.realpath(__file__)), "curseCache")
            else:
                print_text("Portable data dir not supported for interpreter environment")
                sys.exit(2)

    if not cache_path.exists():
        cache_path.mkdir(parents=True)

    if not minecraft_path.exists():
        minecraft_path.mkdir()

    if not mods_path.exists():
        mods_path.mkdir()

    sess = requests.session()

    i = 1
    try:
        i_len = len(manifest_json['files'])
    except KeyError as e:
        print_text('I got a KeyError - reason %s' % str(e))
        print_text("Manifest Error. Make sure you selected a valid pack manifest.json")
        return None

    print_text("Cached files are stored here:\n %s\n" % cache_path)
    print_text("%d files to download" % i_len)

    for dependency in manifest_json['files']:
        dep_cache_dir = cache_path / str(dependency['projectID']) / str(dependency['fileID'])
        if dep_cache_dir.is_dir():
            # File is cached
            dep_files = [f for f in dep_cache_dir.iterdir()]
            if len(dep_files) >= 1:
                dep_file = dep_files[0]
                target_file = minecraft_path / "mods" / dep_file.name
                shutil.copyfile(str(dep_file), str(target_file))
                print_text("[%d/%d] %s (cached)" % (i, i_len, target_file.name))

                i += 1

                # Cache access is successful,
                # Don't download the file
                continue

        # File is not cached and needs to be downloaded
        project_response = sess.get("http://minecraft.curseforge.com/mc-mods/%s"
                                    % (dependency['projectID']), stream=True)
        project_response.url = project_response.url.replace('?cookieTest=1', '')
        file_response = sess.get("%s/files/%s/download"
                                 % (project_response.url, dependency['fileID']), stream=True)
        while file_response.is_redirect:
            source = file_response
            file_response = sess.get(source, stream=True)
        file_path = Path(file_response.url)
        file_name = unquote(file_path.name)
        print_text("[%d/%d] %s" % (i, i_len, file_name))
        with open(str(minecraft_path / "mods" / file_name), "wb") as mod:
            mod.write(file_response.content)

        # Try to add file to cache.
        if not dep_cache_dir.exists():
            dep_cache_dir.mkdir(parents=True)
        with open(str(dep_cache_dir / file_name), "wb") as mod:
            mod.write(file_response.content)

        i += 1

    # This is not available in curse-only packs
    if 'directDownload' in manifest_json:
        i = 1
        i_len = len(manifest_json['directDownload'])
        programGui.set_output("%d additional files to download." % i_len)
        for download_entry in manifest_json['directDownload']:
            if "url" not in download_entry or "filename" not in download_entry:
                programGui.set_output("[%d/%d] <Error>" % (i, i_len))
                i += 1
                continue
            source_url = urlparse(download_entry['url'])
            download_cache_children = Path(source_url.path).parent.relative_to('/')
            download_cache_dir = cache_path / "directdownloads" / download_cache_children
            cache_target = Path(download_cache_dir / download_entry['filename'])
            if cache_target.exists():
                # Cached
                target_file = minecraft_path / "mods" / cache_target.name
                shutil.copyfile(str(cache_target), str(target_file))

                i += 1

                # Cache access is successful,
                # Don't download the file
                continue
            # File is not cached and needs to be downloaded
            file_response = sess.get(source_url, stream=True)
            while file_response.is_redirect:
                source = file_response
                file_response = sess.get(source, stream=True)
            programGui.set_output("[%d/%d] %s" % (i, i_len, download_entry['filename']))
            with open(str(minecraft_path / "mods" / download_entry['filename']), "wb") as mod:
                mod.write(file_response.content)

            i += 1

    print_text("Unpacking Complete")


if args.gui:
    programGui = DownloadUI()
    if args.manifest is not None:
        programGui.set_manifest(args.manifest)
    programGui.root.mainloop()
else:
    programGui = HeadlessUI()
    if args.manifest is not None:
        do_download(args.manifest)
    else:
        if sys.platform == "win32":
            if compiledExecutable:
                print('C:\someFolder\cursePackDownloader.exe '
                      '--portable '
                      '--nogui '
                      '--manifest ["/path/to/manifest.json"]')
                sys.exit()
            else:
                print(
                    'CMD>"path/to/python" "/path/to/downloader.py" '
                    '--portable '
                    '--nogui '
                    '--manifest ["/path/to/manifest.json"]')
                sys.exit()
