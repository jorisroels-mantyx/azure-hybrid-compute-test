import os
from azure.storage.blob import BlobServiceClient

conn = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
client = BlobServiceClient.from_connection_string(conn)
container = client.get_container_client("test-container")

# Write a file to Azure Blob Storage
print("Uploading...")
container.upload_blob("hello.txt", b"Hello from the GPU server! ", overwrite=True)
print("Upload OK")

# Read it back
print("Downloading...")
data = container.download_blob("hello.txt").readall()
print(f"Read back: {data}")