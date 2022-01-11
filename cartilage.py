import sys
import os
import sqlite3
from mod_python import apache
from mod_python import util
from mod_python import Cookie
from mod_python import Session
from io import StringIO

# Full API list:
# http://modpython.org/live/current/doc-html/pythonapi.html

req = None
db = None
cookie = None
session = None
__tstack = None

def handler(request):
    global req
    global db
    global cookie
    global session
    global __tstack

    args = {}
    __tstack = []

    # Get request obj
    req = request

    # get cookie object
    cookie = Cookie

    # get session object
    session = Session

    # Collect any posted form data
    __form_data = util.FieldStorage(req)
    if len(__form_data.items()) > 0:
        for key in __form_data.keys():
            args[key] = __form_data.get(key, None)

    # Get db object if db file specified
    opts = req.get_options()
    if 'dbfile' in opts and os.path.isfile(opts['dbfile']):
        db = sqlite3.connect(opts['dbfile'])

    # Return output
    req.content_type = 'text/html'
    req.write(include(req.uri, args))

    return apache.OK

def include(__file, args={}):
    global req
    global db
    global cookie
    global session
    global __tstack
    __content = []
    __code = ""
    __html_lines = ""
    __current_indent = 0
    __python_block = 0
    __python_block_indent = None
    __tloop = 0

    # Check for template loop. If not, append to stack.
    for t in __tstack:
        if t == __file:
            __tloop = 1
            
    # Check if a loop is detected. If not, get template content (or file open error)
    if __tloop == 1:
        __content.append("<p>Template Loop Detected: " + __file + "</p>")
    else:
        # Add file to template call stack
        __tstack.append(__file)

        # Open file or error
        __path = req.document_root() + __file
        try:
            with open(__path) as __f:
                __content = __f.readlines()
        except IOError:
            __content.append("<p>File not found: " + __file + "</p>")

    # Loop over file content
    for __line in __content:

        # Set/unset python block flags
        if __line[:8] == "<python>":
            __python_block = 1
            __python_block_indent = None
        elif __line[:9] == "</python>":
            __python_block = 0
            __python_block_indent = None

        # Handle python code
        elif __python_block == 1 or __line[0] == ':':

            # Add any previous html lines collected at this point
            if __html_lines != "":
                __code += __add_html_lines(__html_lines, __current_indent)
                __html_lines = ""
                __current_indent = 0

            # Get or adjust for python block indent
            if __python_block == 1:
                if len(__line.rstrip()) > 0:
                    if __python_block_indent == None:
                        __python_block_indent = len(__line) - len(__line.lstrip())
                    __line = __line[__python_block_indent:]

            # Chop off  or replace leading colon if necessary
            if __line[0] == ':':
                if (len(__line[1:]) - len(__line[1:].lstrip()) > 0):
                    __line = __line.replace(':', ' ', 1)
                else:
                    __line = __line[1:]

            # Set html block indent amount
            if len(__line.rstrip(" \r\n")) > 0 and __line.rstrip(" \r\n")[-1] == ':':
                __current_indent = len(__line) - len(__line.lstrip()) + 4
            elif len(__line.rstrip(" \r\n")) > 0:
                __current_indent = len(__line) - len(__line.lstrip())

            # Need to wrap include() in a print statement and maintain the indent
            if __line.lstrip()[:8] == "include(":
                __indent = len(__line) - len(__line.lstrip())
                for __i in range(__indent):
                    __code += " "
                __code += "print(" + __line.lstrip().rstrip() + ")\n"

            # Add python line to code string
            else:
                __code += __line

        # Ignore empty lines
        elif len(__line.rstrip("\r\n")) == 0:

            # Add any previous html lines collected at this point
            __code += __add_html_lines(__html_lines, __current_indent)
            __html_lines = ""
            __current_indent = 0

        # Collect html lines to be added later in a single print statement
        else: 

            # Check if we reduced the indent in the HTML and adjust the 
            # current indent var if necessary
            if __current_indent > 0 and len(__line) - len(__line.lstrip()) < __current_indent:
                __code += __add_html_lines(__html_lines, __current_indent)
                __html_lines = ""
                while __current_indent > 0 and len(__line) - len(__line.lstrip()) < __current_indent:
                    __current_indent = __current_indent - 4 if __current_indent - 4 >= 0 else 0

            # Collect line
            __html_lines += __line

    # Add any remaining html lines collected at this point
    __code += __add_html_lines(__html_lines, __current_indent)

    # Remove vars from scope
    del __html_lines
    del __current_indent
    del __content

    # Execute code and collect output
    __orig_stdout = sys.stdout
    __template_output = sys.stdout = StringIO()
    exec(__code)
    sys.stdout = __orig_stdout
    __html_output = __template_output.getvalue()

    # Remove current template from stack now that it is processed.
    if __tloop == 0:
        __tstack.pop()

    # Uncomment to debug
    #__html_output += "<pre style=\"border:1px solid #000000\">\n"
    #__html_output += __code.replace("<", "&lt;").replace(">", "&gt;")
    #__html_output += "</pre>\n"

    # Return output to caller
    return __html_output

def __add_html_lines(html, indent_len):
    rval = ""
    indent = ""
    subs = []

    for i in range(indent_len):
        indent += " "

    while html.find("{{", 0) > -1:
        left = html.find("{{", 0)
        right = html.find("}}", left + 2)
        if left > -1 and right > -1:
            sub = html[left:right+2]
            subs.append(sub)
            html = html.replace(sub, "[[]]", 1)
        else:
            break

    html = html.replace("\"", "\\\"")
    for sub in subs:
        html = html.replace("[[]]", "\"\"\" + str(" + sub[2:-2] + ") + \"\"\"", 1)

    if len(html) > 0:
        rval += indent
        rval += "print(\"\"\"\n"
        rval += html.rstrip('\r\n')
        rval += "\n"
        rval += indent
        rval += "\"\"\")\n"

    return rval

