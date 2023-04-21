import boto3
import json
import os
import zipfile
from io import BytesIO
from urllib.parse import quote

s3 = boto3.client("s3")
cloudfront = boto3.client("cloudfront")

def lambda_handler(event, context):

    BASE_URL = "<REDACTED>"
    distribution_id = "<REDACTED>"

    # Get the S3 bucket and object key from the event
    bucket = event["Records"][0]["s3"]["bucket"]["name"]
    key = event["Records"][0]["s3"]["object"]["key"]

    # Download the file from S3
    zip_file = BytesIO()
    s3.download_fileobj(bucket, key, zip_file)

    # Check if the file is a ZIP file
    if zipfile.is_zipfile(zip_file):
        # Extract the ZIP file
        with zipfile.ZipFile(zip_file) as zf:
            # Read the README and VERSION files
            try:
                readme_contents = zf.read("README.txt").decode("utf-8")
                version_contents = zf.read("VERSION.txt").decode("utf-8")
            except KeyError:
                print("README or VERSION file not found in the ZIP file.")
                return {
                    "statusCode": 400,
                    "body": json.dumps("README or VERSION file not found in the ZIP file.")
                }

            # Extract the mod name from the key
            mod_name = os.path.splitext(os.path.basename(key))[0]

            # Download the repo.xml file
            repo_xml = BytesIO()
            s3.download_fileobj(bucket, "repo.xml", repo_xml)
            repo_xml_content = repo_xml.getvalue().decode("utf-8")

            # Replace new lines with the desired format
            sanitized_readme_contents = readme_contents.replace('\r\n', '&#13;&#10;').replace('\r', '&#13;&#10;').replace('\n', '&#13;&#10;')

            # Create the mod string
            mod_str = f'<mod name="{mod_name}" version="{version_contents}" url="{BASE_URL + quote(key)}">{sanitized_readme_contents}</mod>'

            # Update or create the mod element
            mod_element_start = repo_xml_content.find(f'<mod name="{mod_name}"')
            if mod_element_start != -1:
                # Update the existing mod element
                mod_element_end = repo_xml_content.find('</mod>', mod_element_start) + len('</mod>')
                repo_xml_content = repo_xml_content[:mod_element_start] + mod_str + repo_xml_content[mod_element_end:]
            else:
                # Create a new mod element
                mod_list_end = repo_xml_content.find('</mod_list>')
                repo_xml_content = repo_xml_content[:mod_list_end] + '  ' + mod_str + '\n' + repo_xml_content[mod_list_end:]

            # Upload the updated repo.xml file to S3
            repo_xml = BytesIO(repo_xml_content.encode('utf-8'))
            s3.upload_fileobj(repo_xml, bucket, "repo.xml")

            # Clone the repo.xml file to mods/repo.xml
            s3.copy_object(Bucket=bucket, CopySource=bucket + "/repo.xml", Key="mods/repo.xml")


            # Invalidate the CloudFront cache for the repo.xml file and the mods/repo.xml file
            cloudfront.create_invalidation( DistributionId=distribution_id, InvalidationBatch={ 'Paths': { 'Quantity': 2, 'Items': [ '/repo.xml', '/mods/repo.xml' ] }, 'CallerReference': 'ovgme-repo-xml-invalidation' } )

            # Invalidate the CloudFront cache for the mod file
            cloudfront.create_invalidation( DistributionId=distribution_id, InvalidationBatch={ 'Paths': { 'Quantity': 1, 'Items': [ f'/{quote(key)}' ] }, 'CallerReference': 'ovgme-mod-invalidation' } )

    else:
        print("The file is not a ZIP file.")

    return {
        "statusCode": 200,
        "body": json.dumps("Function executed successfully.")
    }
