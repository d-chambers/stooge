"""Write the first reproducible output for this project."""

from local import a010_first_output

if __name__ == "__main__":
    # Keep the starter directly executable without relying on Stooge.
    a010_first_output.parent.mkdir(parents=True, exist_ok=True)
    a010_first_output.write_text("Hello from {{ project_name }}!\n")
