import tkinter as tk

from .gui import AnyDoc2MDApp


def main():
    root = tk.Tk()
    AnyDoc2MDApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
