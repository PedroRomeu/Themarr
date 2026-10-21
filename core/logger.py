import queue

log_queue = queue.Queue()

class LogRedirector:
    def __init__(self, original_terminal):
        self.terminal = original_terminal
        self.capture = True

    def write(self, text):
        if self.terminal:
            try:
                self.terminal.write(text)
                self.terminal.flush()
            except (UnicodeEncodeError, OSError):
                # A console that cannot encode emojis must not break the worker thread
                pass

        if self.capture:
            clean_text = text.replace('\r', '\n')
            if clean_text:
                log_queue.put(clean_text)

    def flush(self):
        if self.terminal:
            self.terminal.flush()