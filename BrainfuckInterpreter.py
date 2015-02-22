import sys

import time

from struct import calcsize
from array import array
from math import log

BRAINFUCK_SYMBOLS = {
    ">": True,
    "<": True,
    "+": True,
    "-": True,
    ".": True,
    ",": True,
    "[": True,
    "]": True
}


## Behaviour of the input function when encountering an end of file.
## Bf does not have an official convention on what to do with an EOF
## on input, so we will have to implement several options.
# Handle an EOF as a zero value
EOF_AS_0 = 0
# Handle an EOF as a -1 value. This is equivalent to 255 in an unsigned byte.
EOF_AS_MINUS_1 = 1
# Handle an EOF by not changing the value at the pointer at all.
EOF_AS_UNCHANGED = 2

class UnmatchedBracket(Exception):
    def __init__(self, char, charPos):
        self.char = char
        self.charPos = charPos

    def __str__(self):
        return ("InterpreterError: Unmatched parenthesis '{0}'"
                "at position {1}".format(self.char, self.charPos))


# TODO:
#   -   Have a changeable data type and data size
#   -   Have toggleable wrapping around when decreasing a value below 0
#       or increasing it beyond 255 (or the current maximal value)
#   -   Make it possible to set up an limit for the maximum length of the array
class Interpreter(object):
    def __init__(self, filehandle,
                 initSize=300000, arrayLimit=None, extendSize=1000,
                 stdin = sys.stdin, stdout = sys.stdout,
                 wrapAround = True,
                 newline_as_eof = False, handle_eof = EOF_AS_UNCHANGED,
                 dataType = "B", dataSize = 2**8):

        self.filehandle = filehandle

        if not (arrayLimit is None) and arrayLimit < initSize:
            raise RuntimeError("The array limit cannot be below the initial array size!")

        self.arrayLimit = arrayLimit

        if log(dataSize, 2) % 1 != 0:
            raise RuntimeError("Data size should be of the form '2**a'")

        if 256**calcsize(dataType) != dataSize:
            raise Warning("Size of data type ({0}) is not the same as the given size ({1} vs {2}). "
                          "Setting latter to former".format(dataType, 256**calcsize(dataType), dataSize))
            self._dataSize = calcsize(dataType)
        else:
            self._dataSize = dataSize

        self._wrapAround = wrapAround
        self._dataType = dataType

        self._handle_eof = handle_eof
        assert self._handle_eof in (EOF_AS_0, EOF_AS_MINUS_1, EOF_AS_UNCHANGED)

        # If this flag is set to true, then \n will be
        # interpreted as an end of file when reading from
        # stdin. This can be useful when you use sys.stdin and
        # pressing enter in the console creates a newline character.
        self._newline_as_eof = newline_as_eof

        self.array = array(self._dataType, (0 for i in xrange(initSize)))

        self.pointer = 0

        self._extendSize = extendSize

        self.stdin = stdin
        self.stdout = stdout

        self._openedBrackets = []
        self._parsedCmds = 0

        self._fread = self.filehandle.read
        self._ftell = self.filehandle.tell
        self._fseek = self.filehandle.seek

    def run(self):
        while True:
            endOfFile = self.interpret_next_cmd()
            if endOfFile:
                break

    def run_hook(self, hookFunction, eofFunction = None):
        while True:
            keepRunning = hookFunction(self)

            endOfFile = self.interpret_next_cmd()
            if endOfFile and not (eofFunction is None):
                eofFunction(self)

            if not keepRunning or endOfFile:
                break

    def interpret_next_cmd(self):
        cmd = self._fread(1)
        #print cmd
        if len(cmd) == 0:
            return True
            ##raise EOFError("Reached end of file.")

        self._parsedCmds += 1

        if cmd == "<":
            self.change_pointer(-1)
        elif cmd == ">":
            self.change_pointer(+1)
        elif cmd == "-":
            self.add_to_pointer_value(-1)
        elif cmd == "+":
            self.add_to_pointer_value(+1)
        elif cmd == ",":
            self.input_char()
        elif cmd == ".":
            self.output_char()
        elif cmd == "[":
            startpos = self._ftell()

            if self.array[self.pointer] == 0:
                # If the current pointer value is 0, we will fast forward
                # to the point after the next closing bracket.
                char = self._fread(1)

                # While looking for the matching closing bracket, we need to ignore
                # all balanced brackets. This means that for each opening bracket
                # we encounter we will skip one closing bracket.
                openedBrackets = 0
                while len(char) != 0:
                    if char == "]" and openedBrackets == 0:
                        break
                    elif char == "[":
                        openedBrackets += 1
                    elif char == "]":
                        openedBrackets -= 1

                    char = self._fread(1)
                    #print char
                #print "ok", self._ftell(), char

                # A char length of 0 means that we have reached the end of file.
                # The opening bracket has no matching closing bracket, so
                # we will raise an exception.
                if len(char) == 0:
                    raise UnmatchedBracket("[", startpos-1)
            else:
                # We will store the position of the brackets we ecountered in
                # a list. This saves us the hassle of searching the file backwards.
                self._openedBrackets.append(startpos)

        elif cmd == "]":
            # A closing bracket signals the end of a loop.

            startpos = self._ftell()
            if len(self._openedBrackets) == 0:
                # An empty list of opened brackets means that the closing bracket
                # is standing alone without a matching opening bracket.
                raise UnmatchedBracket("]", startpos-1)
            else:
                if self.array[self.pointer] == 0:
                    # We will now leave this loop and remove the last opening bracket.
                    self._openedBrackets.pop()
                else:
                    # If the pointer value is not 0, we will go back to the latest
                    # open bracket to repeat the execution of code.
                    lastPos = self._openedBrackets[-1]

                    self._fseek(lastPos)
        return False

    def _peek(self, pos):
        curr = self.filehandle.tell()
        self.filehandle.seek(pos)
        char = self.filehandle.read(1)

        self.filehandle.seek(curr)
        return char

    def add_to_pointer_value(self, change):
        # Although this is not an official rule, we will wrap around the
        # value at the pointer so that it stays in the 0-255 range, or
        # whatever the current data size is.
        self.array[self.pointer] = (self.array[self.pointer] + change) % 256


    def change_pointer(self, change):
        self.pointer += change
        if self.pointer < 0: self.pointer = 0

        self.__check_pointer_limit()


    def output_char(self):
        char = chr(self.array[self.pointer])
        self.stdout.write(char)

    def input_char(self):
        #print "Do Input!"
        char = self.stdin.read(1)
        if (char == "" or
                (self._newline_as_eof and char == "\n")):

            if self._handle_eof == EOF_AS_0:
                self.array[self.pointer] = 0
            elif self._handle_eof == EOF_AS_MINUS_1:
                self.array[self.pointer] = 255
            elif self._handle_eof == EOF_AS_UNCHANGED:
                pass
        else:
            self.array[self.pointer] = ord(char)%256


    def __check_pointer_limit(self):
        # If the pointer has went beyond the array limits,
        # we need to add new elements to the array.
        if (self.pointer == len(self.array)
                and self.arrayLimit is None):

            # or self.pointer < self.arrayLimit)):
            self.array.extend((0 for i in xrange(self._extendSize)))


if __name__ == "__main__":
    from cStringIO import StringIO
    from timeit import default_timer

    # This object is an example of a way to implement a function
    # that hooks into the interpreter and does things.
    # The debug function
    def debug(interp):
        pos = interp.filehandle.tell()
        char = interp._peek(pos)

        if char in BRAINFUCK_SYMBOLS:
            print char

        if interp._parsedCmds > 1e7:
            return False
        return True

    # This program takes 12 characters from stdin and puts them into stdout.
    # In this case, we set stdin to be a file-like object containing a string.
    # stdoutput is a file-like object that will hold the output of the bf program.
    filehandle = StringIO("++++++++++++[>,.<-]")

    stdinput = StringIO("Hello World!")
    stdoutput = StringIO()

    brainf = Interpreter(filehandle, stdout=stdoutput,
                         newline_as_eof=True,  handle_eof=EOF_AS_MINUS_1)


    start = default_timer()
    print "starting..."
    brainf.run()#_hook(debug)
    print "BF Output:", stdoutput.getvalue()

    # We can output the values of the first 10 cells like this.
    print brainf.array[0:10]

    # We can calculate some statistics about the performance of the bf program
    timeTaken = default_timer()-start
    print "Time taken: {0} seconds".format(timeTaken)
    print "{0} instruction(s) per second".format(brainf._parsedCmds/timeTaken)