#!/bin/bash
# Minify script to shrink CSS

echo "Minifying CSS"
java -jar yuicompressor-2.4.7.jar --type css -v -o 's/style.min.css' s/style.css
