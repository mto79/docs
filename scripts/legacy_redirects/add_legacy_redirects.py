import fileinput
import re
import json
import os
from collections import defaultdict
from pathlib import Path

# This script is still very much a work in progress.
# It does a pretty good job matching "new" style urls using a combination of
# scraped Docs 1.0 site data, and the legacy_redirects_metadata.json file.
# "Old" style urls have had initial work done to map them, but since 
# we don't currently have any docs live that used "old" style urls,
# this code is commented out until it's needed (and will need to be developed further)

ANSI_STOP = '\033[0m'
ANSI_BOLD = '\033[1m'
ANSI_BLUE = '\033[34m'
ANSI_GREEN = '\033[32m'
ANSI_YELLOW = '\033[33m'
ANSI_RED = '\033[31m'

NEW_URLS_REMOVED_FILES = ['genindex', 'introduction', 'conclusion', 'whats_new']
OLD_URLS_REMOVED_FILES = ['toc']

def determine_url_scheme(url):
  if re.search(r'\.\d+\.html', url) or 'toc.html' in url:
    return 'old'
  else:
    return 'new'

def add_urls_to_output(url, path, output):
  output[str(path)].append(url);

def write_redirects_to_mdx_files(output):
  written = 0
  for filepath in Path('product_docs/docs').rglob('*.mdx'):
    redirects = output[str(filepath)]
    in_frontmatter = False
    injected_redirects = False
    in_existing_redirect_section = False

    for line in fileinput.input(files=[filepath], inplace=1):
      if not injected_redirects and line.startswith('---'):
        if in_frontmatter and redirects:
          written = written + 1
          # print redirects at the end of the frontmatter
          print('legacyRedirectsGenerated:')
          print('  # This list is generated by a script. If you need add entries, use the `legacyRedirects` key.')
          for redirect in redirects:
            relative_redirect = redirect.split('https://www.enterprisedb.com')[1]
            print('  - "{}"'.format(relative_redirect))
          injected_redirects = True
        in_frontmatter = True

      # block existing legacyRedirects from being written back out
      if line.startswith('legacyRedirectsGenerated:'):
        in_existing_redirect_section = True
      elif in_existing_redirect_section and not (line.startswith('  -') or line.startswith('  #')):
        in_existing_redirect_section = False

      if not in_existing_redirect_section:
        print(line, end="")
  return written

# These functions are only used by the commented out "old" url style handling

def title_from_frontmatter(filepath):
  mdx_file = open(filepath)
  for line in mdx_file:
    if line.startswith('title:'):
      mdx_file.close()
      return line.split('title:')[1].strip().replace('"', '')
  mdx_file.close()

def headings_from_mdx(filepath):
  headings = []
  heading_re = re.compile(r'^#+ ')
  mdx_file = open(filepath)
  for line in mdx_file:
    if heading_re.match(line):
      headings.append(
        normalize_title(heading_re.sub('', line))
      )
  mdx_file.close()
  return headings

def normalize_title(title):
  title = re.sub(r'^\d*\.?\d*\.?\d*\.?\d*\s', '', title.strip())
  title = re.sub(r'[\u2000-\u206F\u2E00-\u2E7F\\\'\-!"#$%&()*+,./:;<=>?@[\]^`{|}~’]', '', title)
  title = title.lower().replace(' ', '').replace('*', '').replace('_', '').replace("\\", '').replace('™','').replace('®','')
  return title

def determine_root_mdx_file(docs_path, mdx_folder = None):
  root_path = docs_path
  if mdx_folder:
    root_path += '/{}'.format(mdx_folder)
  index_path = root_path + '/index.mdx'
  if not os.path.exists(index_path):
    return None
  return index_path

def print_report(report_dict):
  for key in report_dict.keys():
    value = report_dict[key]
    print(ANSI_BOLD + key + ANSI_STOP)
    if type(value) is defaultdict:
      print_report(value)
    else:
      print(value)

def print_csv_report(report_dict):
  print('Product,Version,Legacy Docs Folder')
  for product, versions in report_dict.items():
    for version, folders in versions.items():
      for folder, urls in folders.items():
        for url in urls: 
          print('{0},{1},{2},{3}'.format(product, version, folder, url))


metadata_file = open(os.path.dirname(__file__) + '/legacy_redirects_metadata.json')
legacy_metadata_by_product = json.load(metadata_file)
metadata_file.close()

json_file = open(os.path.dirname(__file__) + '/legacy_docs_scrape.json')
scraped_legacy_docs_json = json.load(json_file)
json_file.close()

json_file = open(os.path.dirname(__file__) + '/equivalent_versions.json')
equivalent_versions = json.load(json_file)
json_file.close()

legacy_urls_by_product_version = defaultdict(lambda : defaultdict(list))
for data in scraped_legacy_docs_json:
  if data.get('product'):
    legacy_urls_by_product_version[data.get('product')][data.get('version')].append(data)

processed_count = 0
matched_count = 0
new_count = 0
old_count = 0

missing_folder_count = 0
skipped = 0
no_files = 0

new_failed_to_match = []
new_failed_to_match_count = 0
old_failed_to_match = []
old_failed_to_match_count = 0

no_metadata = defaultdict(lambda : [])
version_missing = defaultdict(lambda : [])
missing_folder_metadata = defaultdict(lambda : defaultdict(set))
no_files_in_folder = defaultdict(lambda : defaultdict(set))

new_failed_to_match = defaultdict(lambda : defaultdict(lambda : defaultdict(list)))
old_failed_to_match = defaultdict(lambda : defaultdict(lambda : defaultdict(list)))

output = defaultdict(lambda : [])

for product in legacy_urls_by_product_version.keys():
  product_data = legacy_urls_by_product_version[product]
  for version in product_data.keys():
    product_version_data = product_data[version]
    effective_version = version
    if product in equivalent_versions and version in equivalent_versions.get(product):
      effective_version = equivalent_versions.get(product).get(version) 

    metadata = legacy_metadata_by_product.get(product)
    if not metadata:
      # no metadata configured for product
      no_metadata[product].append(version)
      continue

    docs_path = 'product_docs/docs/{0}/{1}'.format(metadata['folder_name'], effective_version)
    if not os.path.exists(docs_path):
      # version does not match a version we have
      version_missing[product].append(version)
      continue

    for legacy_page in product_version_data:
      url = legacy_page['url']

      if '/latest/' in url:
        # skip latest urls if they appear, we'll handle those separately
        continue

      url_scheme = determine_url_scheme(url)

      # if product version index page, can match right here
      is_product_index = re.search(r'\/edb-docs\/p\/[\w-]+\/[\d.]+$', url)
      if is_product_index:
        index_path = determine_root_mdx_file(docs_path)
        if index_path:
          add_urls_to_output(url, index_path, output)
          processed_count += 1
          matched_count += 1
          continue

      legacy_folder = '/'.join(url.split('/')[6:8])
      mdx_folder = metadata['subfolders'].get(version)
      if mdx_folder:
        mdx_folder = mdx_folder.get(legacy_folder)
      else:
        mdx_folder = metadata['subfolders'].get('default')
        if mdx_folder:
          mdx_folder = mdx_folder.get(legacy_folder)

      if mdx_folder == 'skip':
        skipped += 1
        continue
      else:
        # At this point we'll say we're attempting to process this record for real
        processed_count += 1

      if mdx_folder == None: # don't want to catch empty string
        # no metadata info for this folder
        missing_folder_count += 1
        missing_folder_metadata[product][version].add(legacy_folder)
        continue

      subfolder_docs_path = docs_path
      if len(mdx_folder) > 0:
        subfolder_docs_path = '{0}/{1}'.format(docs_path, mdx_folder)
        if not os.path.exists(subfolder_docs_path):
          # no files exist in this folder
          no_files += 1
          no_files_in_folder[product][version].add(subfolder_docs_path)
          continue

      subfolder_mdx_files = Path(subfolder_docs_path).rglob('*.mdx')
      product_mdx_files = Path(docs_path).rglob('*.mdx')
      match_found = False

      if url_scheme == 'new':
        new_count += 1

        legacy_page_filename = url.split('/')[-1].replace('.html', '')

        matched_file = []
        for filename in subfolder_mdx_files:
          mdx_page_filename = str(filename).split('/')[-1]
          mdx_page_foldername = str(filename).split('/')[-2]
          if (
            mdx_page_filename == 'index.mdx' and
            mdx_page_foldername != effective_version and
            mdx_page_foldername != mdx_folder
          ):
            mdx_page_filename = mdx_page_foldername
          mdx_page_filename = re.sub(r'^\d*_', '', mdx_page_filename.replace('.mdx', ''))

          if legacy_page_filename == mdx_page_filename:
            add_urls_to_output(url, filename, output)
            matched_count += 1
            match_found = True
            break # TODO handle duplicate url bug that affects some "new" style urls

        # if no match found, check for files we remove
        if legacy_page_filename in NEW_URLS_REMOVED_FILES:
          index_path = determine_root_mdx_file(docs_path, mdx_folder)
          if index_path:
            add_urls_to_output(url, index_path, output)
            matched_count += 1
            match_found = True

        if not match_found:
          new_failed_to_match[product][version][mdx_folder].append(url)
          new_failed_to_match_count += 1
          # print('no match found for {}'.format(url))

      else:
        old_count += 1

        legacy_title = normalize_title(legacy_page['title'])
        legacy_parents = [normalize_title(t) for t in legacy_page['sub_nav']]
        title_matches = []
        heading_matches = []
        heading_matches_exact = []
        for filename in product_mdx_files:
          mdx_title = normalize_title(title_from_frontmatter(filename))
          mdx_headings = headings_from_mdx(filename)
          if legacy_title == mdx_title:
            if str(filename).startswith(subfolder_docs_path):
              output[str(filename)].append(url)
              matched_count += 1
              match_found = True
              break
            else:
              title_matches.append(filename)
          if legacy_title in mdx_headings:
            if mdx_title in legacy_parents:
              heading_matches_exact.append(filename)
            heading_matches.append(filename)

        if not match_found and len(heading_matches) > 0:
          if heading_matches_exact:
            heading_matches = heading_matches_exact
          if len(heading_matches) > 1:
            filtered_matches = [m for m in heading_matches if str(m).startswith(subfolder_docs_path) ]
            if filtered_matches: heading_matches = filtered_matches
          filename = heading_matches[0]
          output[str(filename)].append(url)
          matched_count += 1
          match_found = True
          if len(heading_matches) > 1:
            print("multiple heading match")
            for filename in heading_matches:
              print('{0} ({1}) - {2} - {3}'.format(legacy_title, legacy_parents, filename, url))

        if not match_found and len(title_matches) > 0:
          filename = sorted(title_matches, key=lambda t: len(str(t)))[0]
          output[str(filename)].append(url)
          matched_count += 1
          match_found = True
          if len(title_matches) > 1:
            print("multiple titles match")
            for filename in title_matches:
              print('{0} ({1}) - {2} - {3}'.format(legacy_title, legacy_parents, filename, url))

        # if no match found, check for files we remove
        legacy_page_filename = url.split('/')[-1].replace('.html', '')
        if not match_found and legacy_page_filename in OLD_URLS_REMOVED_FILES:
          index_path = determine_root_mdx_file(docs_path, mdx_folder)
          if index_path:
            output[str(index_path)].append(url)
            matched_count += 1
            match_found = True

        if not match_found:
          ignore_legacy_titles = ['tableofcontents', 'introduction', 'typographicalconventionsusedinthisguide']
          if legacy_title in ignore_legacy_titles: continue
          old_failed_to_match[product][version][mdx_folder].append(url)
          old_failed_to_match_count += 1
          print('{0} ({1}) - {2}'.format(legacy_title, legacy_parents, url))


print("\n{0}================ Report ================{1}".format(ANSI_BLUE, ANSI_STOP))
print("\n{0}-- No Metadata Configured (Not Processed) --{1}".format(ANSI_YELLOW, ANSI_STOP))
print_report(no_metadata)
print("\n{0}-- Version Missing (Not Processed) --{1}".format(ANSI_YELLOW, ANSI_STOP))
print_report(version_missing)
print("\n{0}-- Missing Folder in Metadata --{1}".format(ANSI_RED, ANSI_STOP))
print_report(missing_folder_metadata)
print("\n{0}-- No Folder --{1}".format(ANSI_RED, ANSI_STOP))
print_report(no_files_in_folder)

print("\n{0}-- Summary --{1}".format(ANSI_GREEN, ANSI_STOP))
print('matched {0} of {1} urls processed'.format(matched_count, processed_count))
print('missing folder in metadata: {0}'.format(missing_folder_count))
print('no folder: {0}'.format(no_files))
print('new style urls processed: {}'.format(new_count))
print('new style urls with no match: {}'.format(new_failed_to_match_count))
print('old style urls processed: {}'.format(old_count))
print('old style urls with no match: {}'.format(old_failed_to_match_count))

mdx_files_written = write_redirects_to_mdx_files(output)

mdx_file_count = 0
for path in Path('product_docs/docs').rglob('*.mdx'):
  mdx_file_count += 1

print("wrote to {0} of {1} mdx files".format(mdx_files_written, mdx_file_count))
# print_csv_report(new_failed_to_match)
