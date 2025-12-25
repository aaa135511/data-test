import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import pandas as pd
import threading
import os
import re


# --- CORE DATA PROCESSING LOGIC (FINAL CORRECTED MELT OPERATION) ---

def parse_stock_value(value):
    """
    Custom function to parse special stock strings like '10+'.
    """
    if pd.isna(value):
        return 0
    s_value = str(value).strip()
    if s_value.isdigit():
        return int(s_value)
    match = re.match(r'(\d+)', s_value)
    if match:
        return int(match.group(1))
    return 0


def process_inventory_files(file_paths, status_callback):
    """
    Reads four files and updates inventory, using a corrected and precise
    melt operation on the warehouse details file.
    """
    # +++++ DEBUG TARGET +++++
    DEBUG_TARGET_PART_NUM = "WELL000000SWFZ"
    # ++++++++++++++++++++++++

    try:
        status_callback("Step 1/5: Reading input files (optimized)...")

        inventory_df = pd.read_csv(file_paths["inventory"], engine='c', dtype=str)
        sku_map_df = pd.read_csv(file_paths["sku"], engine='c', dtype=str)
        warehouse_map_df = pd.read_csv(file_paths["warehouse_map"], engine='c', dtype=str)
        warehouse_details_df = pd.read_excel(file_paths["warehouse_details"], engine='openpyxl', dtype=str)

        status_callback("Files loaded successfully.")

        for df in [inventory_df, sku_map_df, warehouse_map_df, warehouse_details_df]:
            df.columns = df.columns.str.strip()
        status_callback("File headers cleaned.")

        INV_ID = 'Supplier ID'
        INV_PART = 'Supplier Part#'
        SKU_ITEM_CODE = 'Item Code'
        WH_MAP_CODE = 'B2B Warehouse Code'
        WH_DETAIL_ITEM_CODE = 'Item Code'

        if 'in stock' in inventory_df.columns:
            INV_STOCK = 'in stock'
        elif 'In Stock' in inventory_df.columns:
            INV_STOCK = 'In Stock'
        else:
            raise KeyError("The Inventory file must contain a column named 'in stock' or 'In Stock'.")

        inventory_df['original_stock'] = pd.to_numeric(inventory_df[INV_STOCK], errors='coerce').fillna(0).astype(int)
        inventory_df['new_stock'] = inventory_df['original_stock']

        status_callback("Step 2/5: Building cleaned lookup dictionaries...")

        # --- Data Cleaning on Key Columns ---
        sku_map_df[INV_PART] = sku_map_df[INV_PART].str.strip()
        sku_map_df[SKU_ITEM_CODE] = sku_map_df[SKU_ITEM_CODE].str.strip()
        warehouse_map_df[INV_ID] = warehouse_map_df[INV_ID].str.strip()
        warehouse_map_df[WH_MAP_CODE] = warehouse_map_df[WH_MAP_CODE].str.strip()
        warehouse_details_df[WH_DETAIL_ITEM_CODE] = warehouse_details_df[WH_DETAIL_ITEM_CODE].str.strip()

        part_to_item_map = sku_map_df.set_index(INV_PART)[SKU_ITEM_CODE].to_dict()
        supplier_to_wh_map = warehouse_map_df.groupby(INV_ID)[WH_MAP_CODE].apply(list).to_dict()

        # --- CRITICAL FIX: Precisely define which columns are warehouses ---
        # Identify columns that are NOT warehouse codes
        non_warehouse_cols = [col for col in ['Item Code', '店铺Code', '可售库存'] if
                              col in warehouse_details_df.columns]
        # Identify columns that ARE warehouse codes by excluding the ones above
        warehouse_cols = [col for col in warehouse_details_df.columns if col not in non_warehouse_cols]

        warehouse_details_long = pd.melt(
            warehouse_details_df,
            id_vars=[WH_DETAIL_ITEM_CODE],
            value_vars=warehouse_cols,  # This is the fix: only melt the actual warehouse columns
            var_name=WH_MAP_CODE,
            value_name='warehouse_stock_raw'
        )
        # --------------------------------------------------------------------

        warehouse_details_long['new_stock_value'] = warehouse_details_long['warehouse_stock_raw'].apply(
            parse_stock_value)
        warehouse_details_long[WH_MAP_CODE] = warehouse_details_long[WH_MAP_CODE].str.strip()
        stock_lookup_map = warehouse_details_long.set_index([WH_DETAIL_ITEM_CODE, WH_MAP_CODE])[
            'new_stock_value'].to_dict()

        status_callback("Step 3/5: Iterating through inventory to find the best stock...")

        updated_items = []

        for index, row in inventory_df.iterrows():
            part_num = str(row[INV_PART]).strip()
            supplier_id = str(row[INV_ID]).strip()

            is_debug_target = (part_num == DEBUG_TARGET_PART_NUM)
            if is_debug_target:
                print("\n" + "=" * 50)
                print(f"DEBUGGING FOR TARGET: Part#='{part_num}', SupplierID='{supplier_id}'")
                print("=" * 50)

            item_code = part_to_item_map.get(part_num)
            if is_debug_target:
                print(f"[DEBUG] 1. Looked up Part# '{part_num}' in sku_map.")
                print(f"   -> Found Item Code: {item_code}")
            if not item_code:
                continue

            possible_wh_codes = supplier_to_wh_map.get(supplier_id)
            if is_debug_target:
                print(f"[DEBUG] 2. Looked up SupplierID '{supplier_id}' in warehouse_map.")
                print(f"   -> Found B2B Warehouse Codes: {possible_wh_codes}")
            if not possible_wh_codes:
                continue

            found_stocks = []
            if is_debug_target:
                print("[DEBUG] 3. Searching for stock in warehouse_details for each code:")

            for wh_code in possible_wh_codes:
                clean_wh_code = str(wh_code).strip()
                lookup_key = (item_code, clean_wh_code)
                stock = stock_lookup_map.get(lookup_key)

                if is_debug_target:
                    print(f"   - Trying key: {lookup_key}")
                    print(f"     -> Stock found in map: {stock}")

                if stock is not None:
                    found_stocks.append(stock)

            final_new_stock = max(found_stocks) if found_stocks else 0

            if is_debug_target:
                print(f"[DEBUG] 4. All found stock values: {found_stocks}")
                print(f"[DEBUG] 5. Determined max stock value: {final_new_stock}")
                print("=" * 50 + "\n")

            old_stock = row['original_stock']
            if final_new_stock != old_stock:
                inventory_df.at[index, 'new_stock'] = final_new_stock

                winning_wh = 'N/A'
                for wh_code in possible_wh_codes:
                    if stock_lookup_map.get((item_code, str(wh_code).strip())) == final_new_stock:
                        winning_wh = wh_code
                        break

                log_entry = (
                    f"UPDATED: Part#={part_num}, ItemCode={item_code}, SupplierID={supplier_id}\n"
                    f"         (Found max stock={final_new_stock} in WH_Code={winning_wh}. Old Stock={old_stock})"
                )
                updated_items.append(log_entry)

        status_callback("Step 4/5: Finalizing results...")

        if updated_items:
            status_callback("\n--- Inventory Update Details ---\n" + "\n".join(updated_items))
        else:
            status_callback("\n--- No inventory changes detected. ---")

        inventory_df[INV_STOCK] = inventory_df['new_stock']
        inventory_df.drop(columns=['original_stock', 'new_stock'], inplace=True)

        status_callback("\nStep 5/5: Processing complete. Ready to export.")
        return inventory_df

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
        self.root.geometry("950x650")

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
        self.create_file_selector(files_frame, "inventory", "Inventory File (.csv)", 0)
        self.create_file_selector(files_frame, "sku", "SKU Map File (.csv)", 1)
        self.create_file_selector(files_frame, "warehouse_map", "Warehouse Map File (.csv)", 2)
        self.create_file_selector(files_frame, "warehouse_details", "Warehouse Details File (.xlsx)", 3)

        process_frame = tk.LabelFrame(main_frame, text="2. Process & Export", padx=10, pady=10)
        process_frame.pack(fill=tk.X, expand=True, pady=10)

        self.process_button = tk.Button(process_frame, text="Update Inventory", command=self.start_processing,
                                        state=tk.DISABLED, font=("Helvetica", 10, "bold"))
        self.process_button.pack(pady=5, ipadx=10, ipady=4)

        self.export_button = tk.Button(process_frame, text="Export Updated Inventory (.csv)", command=self.export_data,
                                       state=tk.DISABLED)
        self.export_button.pack(pady=5)

        status_frame = tk.LabelFrame(main_frame, text="Status & Update Log", padx=10, pady=10)
        status_frame.pack(fill=tk.BOTH, expand=True)

        self.status_log = scrolledtext.ScrolledText(status_frame, height=15, state=tk.DISABLED, wrap=tk.WORD)
        self.status_log.pack(fill=tk.BOTH, expand=True)
        self.log_status("Welcome! Please import the four required files.")

    def create_file_selector(self, parent, key, text, row):
        label = tk.Label(parent, text=text + ":")
        label.grid(row=row, column=0, sticky="w", pady=2)
        self.labels[key] = tk.Label(parent, text="No file selected", fg="grey", anchor="w", width=80)
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
        self.status_log.config(state=tk.NORMAL)
        self.status_log.delete('1.0', tk.END)
        self.log_status("Starting inventory update process...")

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
                    self.log_status(f"\nSuccessfully exported file to: {save_path}")
                    messagebox.showinfo("Success", "File has been exported successfully!")
                except Exception as e:
                    self.log_status(f"\nError exporting file: {e}")
                    messagebox.showerror("Export Error", f"Could not save the file.\nError: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = InventoryUpdaterApp(root)
    root.mainloop()