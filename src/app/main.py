import tkinter as tk


def main() -> None:
    root = tk.Tk()
    root.title("UI App")
    root.geometry("360x200")

    label = tk.Label(root, text="Hello from a cross-platform UI app!", padx=20, pady=20)
    label.pack()

    def on_click() -> None:
        label.config(text="Thanks for clicking!")

    button = tk.Button(root, text="Click me", command=on_click)
    button.pack(pady=10)

    root.mainloop()


if __name__ == "__main__":
    main()
