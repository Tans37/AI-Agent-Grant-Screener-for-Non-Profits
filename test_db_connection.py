import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

def test_connection():
    try:
        conn = mysql.connector.connect(
            host=os.getenv("MYSQL_HOST"),
            user=os.getenv("MYSQL_USER"),
            password=os.getenv("MYSQL_PASSWORD"),
            database=os.getenv("MYSQL_DB"),
            port=os.getenv("MYSQL_PORT")
        )

        if conn.is_connected():
            print(f"Successfully connected to the database: {os.getenv('MYSQL_DB')}")
            cursor = conn.cursor(dictionary=True)
            
            # Inspect the specific view
            view_name = "Grant_Opportunities" 
            print(f"\nInspecting view: {view_name}")
            try:
                cursor.execute(f"DESCRIBE {view_name}")
                columns = cursor.fetchall()
                print("Columns:")
                for col in columns:
                    print(f"- {col['Field']} ({col['Type']})")
                
                print(f"\nFetching one 'LOI Backlog' row from {view_name}:")
                cursor.execute(f"SELECT * FROM {view_name} WHERE StageName = 'LOI Backlog' LIMIT 1")
                row = cursor.fetchone()
                print(row)

                
            except mysql.connector.Error as err:
                 print(f"Error inspecting view '{view_name}': {err}")
            
            cursor.close()
            conn.close()
            
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        if "Unknown database" in str(err):
            print("Double check the database name case sensitivity.")

if __name__ == "__main__":
    test_connection()
