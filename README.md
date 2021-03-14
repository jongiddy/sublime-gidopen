# Sublime GidOpen

Context menu that runs inside Sublime Text.

## Install

Clone this repo into your Sublime Text packages repository.

For example:
```
cd ~/.config/sublime-text-3/Packages
git clone git@github.com:jongiddy/sublime-gidopen.git
```

## Update

Update by pulling the latest version.

```
cd ~/.config/sublime-text-3/Packages/sublime-gidopen
git pull
```

## Use

Right-click on a point in the text. If the text around the point looks 
like a filename, then a menu item will be visible to open the file. If
line and column information is also available, the menu will offer to
go to the specific location.

If the filename is not correctly selected, select the correct filename
and right-click on the selected text.  In this case, if the file does
not exist, the menu will offer to create the file.
