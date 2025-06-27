"""
This script connects via SSH to a remote ArchivesSpace EAD exporter server,
extracts error logs for a given date, and prints an email-ready summary of
problematic resources with URLs.

The script prints the results to the console for manual copy/paste into email.

Requires the following environment variables:
  - EAD_SERVER
  - ASPACE_USER
  - ASPACE_PASS
  - ASPACE_API_URL
"""

import paramiko
import datetime
import requests
import os
import re
import getpass

# SSH Configuration
server = os.getenv("EAD_SERVER")
username = os.getenv("ASPACE_USER")
password = getpass.getpass("Enter your SSH password: ")

# ArchivesSpace API Configuration
aspace_pass = os.getenv("ASPACE_PASS")
aspace_base_url = os.getenv("ASPACE_API_URL")

if not aspace_base_url:
    print("Error: ASPACE_API_URL environment variable not set.")
    exit()

# Generate today's date for log filename and email subject
today_date = datetime.date.today()
formatted_date = today_date.strftime("%A %B %d, %Y")  # Outputs human-readable date e.g. Wednesday February 7, 2025
default_log_filename = f"exporter_app.out-{today_date.strftime('%Y-%m-%d')}"

# Ask user for export log file (defaults to current date)
# If you wish to review a different date's logs, enter the entire file name in this format: exporter_app.out-YYYY-MM-DD
user_input = input(f"\nEnter the export log filename (default: {default_log_filename}): ").strip()
log_filename = user_input if user_input else default_log_filename

# Extract date from log filename to determine date range
date_match = re.search(r"(\d{4}-\d{2}-\d{2})", log_filename)
if date_match:
    log_date = date_match.group(1)
    log_datetime = datetime.datetime.strptime(log_date, "%Y-%m-%d").date()
    yesterday = (log_datetime - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    today = log_date
else:
    print("Error: Could not determine date from filename. Using default date range.")
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    today = today_date.strftime("%Y-%m-%d")

# Define the grep command to get errors from the SSH server
log_path = f"/home/eadexport/archivesspace_export_service/exporter_app/logs/{log_filename}"
grep_command = f'grep -E "{yesterday}|{today}T0[0-6]" {log_path} | grep "ERROR" | grep -oP "/repositories/\\K\\d+(?=/resources/\\d+)|(?<=/resources/)\\d+" | sed "N;s/\\n/ /" | sort -n | uniq'

# Start SSH connection
try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # Trust the server
    ssh.connect(server, username=username, password=password)

    # Execute grep command remotely
    stdin, stdout, stderr = ssh.exec_command(grep_command)
    
    # Read output
    output = stdout.read().decode().strip()
    errors = stderr.read().decode().strip()

    if errors:
        print(f"Error executing grep command: {errors}")

    print("\n===== Retrieved Repository Errors =====")
    if output:
        print(output)
    else:
        print("No repository errors found.")
        exit()

except Exception as e:
    print(f"SSH Connection Failed: {e}")
    exit()

finally:
    ssh.close()

# Process the repository errors
resources = []
for line in output.splitlines():
    ids = line.strip().split(" ")
    if len(ids) == 2:
        resources.append({"RepositoryID": int(ids[0]), "ResourceID": int(ids[1])})

if not resources:
    print("No repository errors found.")
    exit()

# Generate the email text (replace with your sign-off/name)
email_subject = f"ArchivesSpace Validation Errors :: {formatted_date}"
email_body = """Hello!

Below you'll find a list of collections that encountered errors this morning during the export process. These errors were reported by the application that exports EAD to a Yale ArchivesSpace GitHub repository and generates the public-facing PDF finding aids.

All best,
[YOUR NAME]

"""

# Append errored resources to the email
for resource in resources:
    repository_id = resource["RepositoryID"]
    resource_id = resource["ResourceID"]
    resource_url = f"https://archives.yale.edu/repositories/{repository_id}/resources/{resource_id}"
    email_body += f"{resource_id}, {resource_url}\n"

# Email draft can be copied and pasted simply!
print("\n===== Email Preview =====")
print(email_subject)
print(email_body)
print()