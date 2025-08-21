"""
This script connects via SSH to a remote ArchivesSpace EAD exporter server,
extracts error logs for a given date, and prints an email-ready summary of
problematic resources with URLs.

The script prints the results to the console for manual copy/paste into email.

Requires (env):
- EAD_SSH_HOST
- OR EAD_SERVER
"""

import paramiko
import datetime
import os
import re

# SSH Configuration
host = os.getenv("EAD_SSH_HOST") or os.getenv("EAD_SERVER")
if not host:
    print("Error: set EAD_SSH_HOST (recommended) or EAD_SERVER.")
    exit()

# Read ~/.ssh/config
cfg = paramiko.SSHConfig()
cfg_path = os.path.expanduser("~/.ssh/config")
ssh_params = {"hostname": host}
if os.path.exists(cfg_path):
    with open(cfg_path) as f:
        cfg.parse(f)
    hc = cfg.lookup(host)
    if "hostname" in hc: ssh_params["hostname"] = hc["hostname"]
    if "user" in hc:     ssh_params["username"] = hc["user"]
    if "port" in hc:     ssh_params["port"] = int(hc["port"])
    if "identityfile" in hc: ssh_params["key_filename"] = hc["identityfile"]

# Generate today's date for log filename and email subject
today_date = datetime.date.today()
formatted_date = today_date.strftime("%A %B %d, %Y")
default_log_filename = f"exporter_app.out-{today_date.strftime('%Y-%m-%d')}"

# Ask user for export log file (defaults to current date)
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

# Define a broader grep command to get all early-morning logs
log_path = f"/usr/local/src/archivesspace_export_service/exporter_app/logs/{log_filename}"
grep_command = f'grep -E "{yesterday}|{today}T0[0-6]" {log_path}'

# Start SSH connection
try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(allow_agent=True, look_for_keys=True, timeout=20, **ssh_params)

    stdin, stdout, stderr = ssh.exec_command(grep_command)

    output = stdout.read().decode().strip()
    errors = stderr.read().decode().strip()

    if errors:
        print(f"Error executing grep command: {errors}")

    print("\n===== Retrieved Repository Errors =====")
    if not output:
        print("No repository errors found.")
        exit()

except Exception as e:
    print(f"SSH Connection Failed: {e}")
    exit()

finally:
    ssh.close()

# Process the repository errors
resources = []
last_repo = None
last_resource = None

for line in output.splitlines():
    # Look for resource URI lines
    uri_match = re.search(r"/repositories/(\d+)/resources/(\d+)", line)
    if uri_match:
        last_repo = int(uri_match.group(1))
        last_resource = int(uri_match.group(2))

    # Match error lines of interest
    if "ERROR" in line and (
        "XML cleaning failed" in line
        or "SolrIndexerError" in line
        or "Validation error" in line
    ):
        if last_repo is not None and last_resource is not None:
            resources.append({
                "RepositoryID": last_repo,
                "ResourceID": last_resource
            })
            # Clear after logging to avoid duplicates
            last_repo = None
            last_resource = None

# Remove duplicates
resources = [dict(t) for t in {tuple(d.items()) for d in resources}]

if not resources:
    print("No repository errors found.")
    exit()

# Generate the email text
email_subject = f"ArchivesSpace Validation Errors :: {formatted_date}"
email_body = """Hello!

Below you'll find a list of collections that encountered errors this morning during the export process. These errors were reported by the application that exports EAD to a Yale ArchivesSpace GitHub repository and generates the public-facing PDF finding aids.

All best,  
[YOUR NAME]

---

"""

# Append errored resources
for resource in resources:
    repository_id = resource["RepositoryID"]
    resource_id = resource["ResourceID"]
    resource_url = f"https://archives.yale.edu/repositories/{repository_id}/resources/{resource_id}"
    email_body += f"{resource_url}\n"

# Print the email draft
print("\n===== Email Preview =====")
print(email_subject)
print(email_body)
print("\n---")
print()