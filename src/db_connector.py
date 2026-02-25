import os
import mysql.connector
from typing import List
from .models import Grant
import re

class DBConnector:
    def __init__(self):
        self.host = os.getenv("MYSQL_HOST")
        self.user = os.getenv("MYSQL_USER")
        self.password = os.getenv("MYSQL_PASSWORD")
        self.db_name = os.getenv("MYSQL_DB")
        self.port = os.getenv("MYSQL_PORT")

    def _get_connection(self):
        return mysql.connector.connect(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.db_name,
            port=self.port
        )

    def fetch_backlog_grants(self, limit: int = None) -> List[Grant]:
        """
        Fetches grants matching the configured stage filter.
        Table and stage are set via DB_TABLE and DB_STAGE_FILTER in .env.
        """
        table       = os.getenv("DB_TABLE", "YourSchema.Grant_Opportunities")
        stage_filter = os.getenv("DB_STAGE_FILTER", "LOI Backlog")

        query = f"""
            SELECT
                Id,
                Name,
                Corporate_Kanban_Sort__c,
                Amount,
                Grant_Requirements_Website__c,
                Grant_Focus__c,
                StageName
            FROM {table}
            WHERE StageName = '{stage_filter}'
        """
        
        if limit:
            query += f" LIMIT {limit}"
            
        grants = []
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query)
            rows = cursor.fetchall()
            
            for row in rows:
                # Clean up foundation name from Corporate_Kanban_Sort__c
                # Typically format is "~Foundation Name"
                foundation_raw = row['Corporate_Kanban_Sort__c'] or row['Name']
                foundation_name = foundation_raw.lstrip('~').strip()
                
                # If foundation name still looks like "Name - Date", try to split?
                # For now, keep it simple.
                
                grant = Grant(
                    id=row['Id'],
                    name=row['Name'],
                    foundation_name=foundation_name,
                    amount=row['Amount'],
                    website=row['Grant_Requirements_Website__c'],
                    focus_area=row['Grant_Focus__c'],
                    stage=row['StageName']
                )
                grants.append(grant)
                
            cursor.close()
            conn.close()
            print(f"Fetched {len(grants)} grants from backlog.")
            
        except mysql.connector.Error as err:
            print(f"Error fetching grants: {err}")
            
        return grants
