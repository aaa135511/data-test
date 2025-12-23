import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import pandas as pd
import threading
import os


# --- CORE DATA PROCESSING LOGIC (FINAL ROBUST VERSION) ---

def process_inventory_files(file_paths, status_callback):
    """
    Reads the four input files and updates the inventory stock levels.
    This version fixes the data type mismatch error (int64 vs object)
    by converting all key columns to strings before merging.
    """
    try:
        status_callback("Step 1/5: Reading input files...")

        # Define the key column names
        INV_ID = 'Supplier ID'
        INV_PART = 'Supplier Part#'
        INV_STOCK = 'in stock'
        SKU_PART = 'Supplier Part#'
        SKU_ITEM_CODE = 'Item Code'
        WH_MAP_ID = 'Supplier ID'
        WH_MAP_CODE = 'B2B Warehouse Code'
        WH_DETAIL_ITEM_CODE = 'Item Code'

        # --- Read the files ---
        inventory_df = pd.read_csv(file_paths["inventory"])
        sku_map_df = pd.read_csv(file_paths["sku"])
        warehouse_map_df = pd.read_csv(file_paths["warehouse_map"])
        warehouse_details_df = pd.read_excel(file_paths["warehouse_details"], engine='openpyxl')

        # --- Clean all column headers to remove leading/trailing spaces ---
        inventory_df.columns = inventory_df.columns.str.strip()
        sku_map_df.columns = sku_map_df.columns.str.strip()
        warehouse_map_df.columns = warehouse_map_df.columns.str.strip()
        warehouse_details_df.columns = warehouse_details_df.columns.str.strip()
        status_callback("File headers cleaned automatically.")

        # --- NEW FIX: Standardize data types of key columns BEFORE merging ---
        # This is the crucial fix for the "int64 and object" error.
        # We convert all ID/Code columns to strings to ensure they match perfectly.
        status_callback("Standardizing key column data types to prevent merge errors...")

        # List of dataframes and the key columns to convert in each
        dfs_to_standardize = {
            "Inventory": (inventory_df, [INV_ID, INV_PART]),
            "SKU Map": (sku_map_df, [SKU_PART, SKU_ITEM_CODE]),
            "Warehouse Map": (warehouse_map_df, [WH_MAP_ID]),
            "Warehouse Details": (warehouse_details_df, [WH_DETAIL_ITEM_CODE])
        }

        for name, (df, columns) in dfs_to_standardize.items():
            for col in columns:
                if col in df.columns:
                    df[col] = df[col].astype(str)
                else:
                    # If a key column is missing, we must stop and report it.
                    raise KeyError(f"The required column '{col}' was not found in the {name} file.")

        # Ensure the stock column exists
        if INV_STOCK not in inventory_df.columns:
            if 'In Stock' in inventory_df.columns:
                INV_STOCK = 'In Stock'
            else:
                raise KeyError(
                    f"Critical Error: The inventory file must contain an '{INV_STOCK}' or 'In Stock' column.")

        status_callback("Step 2/5: Transforming warehouse stock data...")
        warehouse_details_long = pd.melt(
            warehouse_details_df,
            id_vars=[WH_DETAIL_ITEM_CODE],
            var_name=WH_MAP_CODE,
            value_name='new_in_stock'
        )

        status_callback("Step 3/5: Merging data tables...")

        # 1. Merge Inventory with SKU Map
        merged_df = pd.merge(inventory_df, sku_map_df, on=INV_PART, how='left')

        # 2. Merge with Warehouse Map
        merged_df = pd.merge(merged_df, warehouse_map_df, on=WH_MAP_ID, how='left')

        # 3. Merge with warehouse details
        final_merged_df = pd.merge(merged_df, warehouse_details_long, on=[SKU_ITEM_CODE, WH_MAP_CODE], how='left')

        status_callback("Step 4/5: Updating stock values...")
        inventory_df[INV_STOCK] = final_merged_df['new_in_stock'].fillna(inventory_df[INV_STOCK])
        inventory_df[INV_STOCK] = pd.to_numeric(inventory_df[INV_STOCK], errors='coerce').fillna(0).astype(int)

        status_callback("Step 5/5: Processing complete. Ready to export.")
        return inventory_df

    except FileNotFoundError as e:
        error_msg = f"Error: File not found - {e.filename}"
        status_callback(error_msg)
        messagebox.showerror("File Not Found", error_msg)
        return None
    except KeyError as e:
        error_msg = f"Error: A required column is missing in one of the files. {e}"
        status_callback(error_msg)
        messagebox.showerror("Column Mismatch", error_msg)
        return None
    except Exception as e:
        error_msg = f"An unexpected error occurred: {e}"
        status_callback(error_msg)
        messagebox.showerror("Error", error_msg)
        return None


# --- GRAPHICAL USER INTERFACE (GUI) - (No changes needed here) ---

class InventoryUpdaterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Inventory Stock Updater")
        self.root.geometry("700x550")

        self.file_paths = {
            "inventory": "",
            "sku": "",
            "warehouse_map": "",
            "warehouse_details": ""
        }
        self.updated_df = None

        main_frame = tk.Frame(root, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        files_frame = tk.LabelFrame(main_frame, text="1. Import Files", padx=10, pady=10)
        files_frame.pack(fill=tk.X, expand=True)

        self.labels = {}
        self.create_file_selector(files_frame, "inventory", "Inventory File (contains 'Supplier Part#')", 0)
        self.create_file_selector(files_frame, "sku", "SKU Map File (also contains 'Supplier Part#')", 1)
        self.create_file_selector(files_frame, "warehouse_map", "Warehouse Map File (contains 'Supplier ID')", 2)
        self.create_file_selector(files_frame, "warehouse_details", "Warehouse Details File (.xlsx)", 3)

        process_frame = tk.LabelFrame(main_frame, text="2. Process & Export", padx=10, pady=10)
        process_frame.pack(fill=tk.X, expand=True, pady=10)

        self.process_button = tk.Button(process_frame, text="Update Inventory", command=self.start_processing,
                                        state=tk.DISABLED)
        self.process_button.pack(pady=5)

        self.export_button = tk.Button(process_frame, text="Export Updated Inventory (.csv)", command=self.export_data,
                                       state=tk.DISABLED)
        self.export_button.pack(pady=5)

        status_frame = tk.LabelFrame(main_frame, text="Status Log", padx=10, pady=10)
        status_frame.pack(fill=tk.BOTH, expand=True)

        self.status_log = scrolledtext.ScrolledText(status_frame, height=8, state=tk.DISABLED)
        self.status_log.pack(fill=tk.BOTH, expand=True)
        self.log_status("Welcome! Please import the four required files.")

    def create_file_selector(self, parent, key, text, row):
        label = tk.Label(parent, text=text + ":")
        label.grid(row=row, column=0, sticky="w", pady=2)
        self.labels[key] = tk.Label(parent, text="No file selected", fg="grey", anchor="w", width=50)
        self.labels[key].grid(row=row, column=1, sticky="ew", padx=5)
        button = tk.Button(parent, text="Browse...", command=lambda: self.select_file(key))
        button.grid(row=row, column=2, sticky="e")
        parent.grid_columnconfigure(1, weight=1)

    def select_file(self, key):
        if key == "warehouse_details":
            filetypes = [("Excel files", "*.xlsx")]
        else:
            filetypes = [("CSV files", "*.csv")]
        filepath = filedialog.askopenfilename(title=f"Select {key.replace('_', ' ')} file", filetypes=filetypes)
        if filepath:
            self.file_paths[key] = filepath
            filename = os.path.basename(filepath)
            self.labels[key].config(text=filename, fg="black")
            self.log_status(f"Loaded '{key}': {filename}")
        self.check_all_files_selected()

    def check_all_files_selected(self):
        if all(self.file_paths.values()):
            self.process_button.config(state=tk.NORMAL)
            self.log_status("All files selected. Ready to process.")
        else:
            self.process_button.config(state=tk.DISABLED)

    def log_status(self, message):
        self.status_log.config(state=tk.NORMAL)
        self.status_log.insert(tk.END, message + "\n")
        self.status_log.see(tk.END)
        self.status_log.config(state=tk.DISABLED)
        self.root.update_idletasks()

    def start_processing(self):
        self.process_button.config(state=tk.DISABLED)
        self.export_button.config(state=tk.DISABLED)
        processing_thread = threading.Thread(target=self.run_processing_logic)
        processing_thread.start()

    def run_processing_logic(self):
        self.updated_df = process_inventory_files(self.file_paths, self.log_status)
        if self.updated_df is not None:
            self.export_button.config(state=tk.NORMAL)
        else:
            self.process_button.config(state=tk.NORMAL)

    def export_data(self):
        if self.updated_df is not None:
            default_filename = "Inventory_UPDATED.csv"
            save_path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv")],
                initialfile=default_filename,
                title="Save Updated Inventory As"
            )
            if save_path:
                try:
                    self.updated_df.to_csv(save_path, index=False)
                    self.log_status(f"Successfully exported file to: {save_path}")
                    messagebox.showinfo("Success", "File has been exported successfully!")
                except Exception as e:
                    self.log_status(f"Error exporting file: {e}")
                    messagebox.showerror("Export Error", f"Could not save the file.\nError: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = InventoryUpdaterApp(root)
    root.mainloop()