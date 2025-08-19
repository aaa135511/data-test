import pandas as pd

def excel_to_markdown(excel_file, markdown_file):
    """
    Reads data from an Excel file and saves it as a Markdown file.

    Args:
        excel_file (str): The name of the input Excel file.
        markdown_file (str): The name of the output Markdown file.
    """
    try:
        # Read the Excel file into a pandas DataFrame. [6, 7, 8]
        # The `read_excel` function can read .xlsx files. [6]
        df = pd.read_excel(excel_file)

        # Convert the DataFrame to a Markdown table. [9]
        # The `to_markdown` function requires the `tabulate` library. [9]
        markdown_table = df.to_markdown(index=False)

        # Write the Markdown table to a file.
        with open(markdown_file, 'w', encoding='utf-8') as f:
            f.write(markdown_table)

        print(f"Successfully converted {excel_file} to {markdown_file}")

    except FileNotFoundError:
        print(f"Error: The file {excel_file} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

# Define the file names
excel_filename = "8.1-8.3系统导出.xlsx"
markdown_filename = "output.md"

# Call the function to perform the conversion
excel_to_markdown(excel_filename, markdown_filename)