import argparse
import os
import glob
import spacy
import en_core_web_trf
from spacy.language import Language
from spacy.tokens import Doc, Token
import re
import sys
import warnings


warnings.filterwarnings("ignore", category=FutureWarning)

block = '\u2588'
Doc.set_extension("redact_names_count", default=0, force=True)
Doc.set_extension("redact_dates_count", default=0, force=True)
Doc.set_extension("redact_phones_count", default=0, force=True)
Doc.set_extension("redact_address_count", default=0, force=True)


def main(input, censor_flags, concept, output, write_stats_to):
    files = get_files(input)
    all_stats = process_files(files, censor_flags, concept, output)
    write_all_stats(all_stats, write_stats_to)


def write_all_stats(all_stats, write_stats_to):
    total_redacted = 0
    final_stats = "       ********** Stats **********\n"
    num_files = len(all_stats)
    for file, stats in all_stats:
        file_total_redacted = sum(stats.values())
        total_redacted += file_total_redacted
        final_stats += f"File Name: {file} \nTotal Redacted items: {file_total_redacted}\n"
        for component, count in stats.items():
            final_stats += f"     Number of {component}: {count}\n"
        final_stats+="\n"
    final_stats += f"Total redacted items across {num_files} files: {total_redacted}"
    if write_stats_to == "stdout":
        sys.stdout.write(final_stats + "\n")
    elif write_stats_to == "stderr":
        sys.stderr.write(final_stats + "\n")
    else:
        stats_dir = os.path.dirname(write_stats_to)
        if stats_dir and not os.path.exists(stats_dir):
            os.makedirs(stats_dir)
        with open(write_stats_to, 'w') as file:
            file.write(final_stats)

def get_files(input):
    all_files = []
    for _glob in input:
        files = glob.glob(_glob, recursive=True)
        all_files += files
    return all_files


def read_file(file_name):
    try:
        with open(file_name, 'r') as file:
            data = file.read()
            return data
    except FileNotFoundError:
        print(f"The file - {file_name} was not found.")
        return ""
    except IOError:
        print(f"The file - {file_name} cannot be read.")
        return ""

def redaction(txt, censor_flags, concept):
    nlp = spacy.load("en_core_web_trf")
    for flag in censor_flags:
        if flag == "names":
            nlp.add_pipe("redact_names", last=True)
        if flag == "dates":
            nlp.add_pipe("redact_dates", last=True)
        if flag == "phones":
            nlp.add_pipe("redact_phones", last=True)
        if flag == "address":
            nlp.add_pipe("redact_address", last=True)
    doc = nlp(txt)
    file_stats = {
        "redacted names": doc._.redact_names_count,
        "redacted dates": doc._.redact_dates_count,
        "redacted phones": doc._.redact_phones_count,
        "redacted addresses": doc._.redact_address_count,
    }
    return doc.text, file_stats


def process_files(files, censor_flags, concept, output_dir):
    all_stats = []
    for file in files:
        txt = read_file(file)
        redacted_txt, file_stats = redaction(txt, censor_flags, concept)
        file_name = file.split('/')[-1]
        all_stats.append((file_name, file_stats))
        output_file_name = file_name + ".censored"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        output_file_path = os.path.join(output_dir, output_file_name)
        with open(output_file_path, "w") as f:
            f.write(redacted_txt)
    return all_stats


def redact_email(email, split_names):
    local_count = 0
    username, domain = email.split('@')
    if any(part.lower() in username.lower() for part in split_names):
        local_count += 1
        return block * len(username) + '@' + domain, local_count
    return email, local_count


def redact_text(text, split_names):
    local_count = 0
    original_text = text
    for part in split_names:
        if part.lower() in text.lower():
            text = re.sub(r'\b\w+\b', lambda m: block * len(m.group()) if part.lower() in m.group().lower() else m.group(), text)
    if text != original_text:
        local_count += 1
    return text, local_count


@Language.component("redact_names")
def redact_names(doc):
    names_redacted_count = 0
    names_entities = [ent.text for ent in doc.ents if ent.label_ == "PERSON"]
    split_names = set()
    for entity in names_entities:
        split_names.update(entity.lower().split())
    redact_list = names_entities + list(split_names)
    redact_list = sorted(redact_list, key=len, reverse=True)
    name_pattern = '|'.join(re.escape(name) for name in redact_list)
    name_regex = re.compile(r'\b(' + name_pattern + r')(\S*)\b', re.IGNORECASE)
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    email_regex = re.compile(email_pattern)
    new_tokens = []
    new_spaces = []
    i = 0
    while i < len(doc):
        email_match = email_regex.match(doc[i:].text)
        if email_match:
            email = email_match.group()
            redacted_email, count = redact_email(email, split_names)
            new_tokens.append(redacted_email)
            new_spaces.append(doc[i + len(email.split()) - 1].whitespace_)
            i += len(email.split())
            names_redacted_count += count
            continue
        name_match = name_regex.match(doc[i:].text)
        if name_match:
            redacted_name = block * len(name_match.group())
            new_tokens.append(redacted_name)
            new_spaces.append(doc[i + len(name_match.group().split()) - 1].whitespace_)
            i += len(name_match.group().split())
            names_redacted_count += 1
        else:
            token_text = doc[i].text
            redacted_text, count = redact_text(token_text, split_names)
            new_tokens.append(redacted_text)
            new_spaces.append(doc[i].whitespace_)
            i += 1
            names_redacted_count += count
    redacted_doc = Doc(doc.vocab, words=new_tokens, spaces=new_spaces)
    redacted_doc._.redact_names_count = names_redacted_count
    return redacted_doc


@spacy.Language.component("redact_dates")
def redact_dates(doc):
    text = doc.text
    dates_redacted_count = 0
    for ent in doc.ents:
        if ent.label_ == "DATE":
            start, end = ent.start_char, ent.end_char
            text = text[:start] + block * (end - start) + text[end:]
            dates_redacted_count += 1
    date_matching_pattern = r'\b(?:\d{1,4}[-/]\d{1,2}[-/]\d{1,4}|\d{1,2}\s(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s?\d{2,4})\b'
    matches = list(re.finditer(date_matching_pattern, text, re.IGNORECASE))
    for match in reversed(matches):
        start, end = match.span()
        if block not in text[start:end]:
            text = text[:start] + block * (end - start) + text[end:]
            dates_redacted_count += 1
    date_field_pattern = r'Date:.*?(?=\n)'
    date_field_match = re.search(date_field_pattern, text)
    if date_field_match:
        start, end = date_field_match.span()
        text = text[:start] + 'Date: ' + block * (end - start - 6) + text[end:]
        dates_redacted_count += 1
    new_tokens = []
    new_spaces = []
    for token in doc:
        if token.idx < len(text):
            new_tokens.append(text[token.idx:token.idx + len(token.text)])
            new_spaces.append(token.whitespace_)
    redacted_doc = Doc(doc.vocab, words=new_tokens, spaces=new_spaces)
    redacted_doc._.redact_dates_count = dates_redacted_count
    return redacted_doc

@Language.component("redact_phones")
def redact_phones(doc):
    phone_pattern = r'(?<!\w)(?:\+?1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\w)'
    text = doc.text
    phones_redaction_count = 0
    matches = list(re.finditer(phone_pattern, text))
    matches.sort(key=lambda x: x.start(), reverse=True)
    for match in matches:
        start, end = match.span()
        text = text[:start] + block * (end - start) + text[end:]
        phones_redaction_count += 1
    new_tokens = []
    new_spaces = []
    for token in doc:
        if token.idx < len(text):
            new_tokens.append(text[token.idx:token.idx + len(token.text)])
            new_spaces.append(token.whitespace_)
    redacted_doc = Doc(doc.vocab, words=new_tokens, spaces=new_spaces)
    redacted_doc._.redact_phones_count = phones_redaction_count
    return redacted_doc


@Language.component("redact_address")
def redact_address(doc):
    text = doc.text
    address_redaction_count = 0
    multiline_address_pattern = (
        r"(?P<full_address>(?:^|\n)(?P<name>[A-Za-z\s]+,\s+[A-Za-z\s]+)?\s*"
        r"(?P<company>[A-Za-z\s]+)?\s*"
        r"(?P<street>\d+\s(?:[A-Za-z]+\s?)+"
        r"(?:St(?:reet)?|Ave(?:nue)?|Blvd|Boulevard|Rd|Road|Dr|Drive|Way|Ln|Lane|Ct|Court|Pl|Place|Broadway)"
        r"(?:,\s?[A-Za-z0-9\s]+)?)\s*"
        r"(?P<city>[A-Za-z\s]+)?,?\s*(?P<state>[A-Z]{2})?\s*(?P<zip>\d{5}(?:-\d{4})?)?)"
    )
    inline_address_pattern = (
        r"\b\d+\s(?:[A-Za-z]+\s?)+"
        r"(?:St(?:reet)?|Ave(?:nue)?|Blvd|Boulevard|Rd|Road|Dr|Drive|Way|Ln|Lane|Ct|Court|Pl|Place|Broadway)"
        r"(?:,\s?[A-Za-z0-9\s]+)?\b"
    )

    matches = list(re.finditer(multiline_address_pattern, text, re.MULTILINE))
    for match in reversed(matches):
        start, end = match.span('full_address')
        address_lines = text[start:end].split('\n')
        redacted_address = '\n'.join(
            block * len(line.rstrip()) + ' ' * (len(line) - len(line.rstrip()))
            if "company" not in match.groupdict() or line.strip() != match.group('company')
            else line
            for line in address_lines
        )
        text = text[:start] + redacted_address + text[end:]
        address_redaction_count += 1
    matches = list(re.finditer(inline_address_pattern, text))
    for match in reversed(matches):
        start, end = match.span()
        text = text[:start] + block * (end - start) + text[end:]
        address_redaction_count += 1

    location_pattern = (
        r"\b(?:[A-Za-z]+(?:\s[A-Za-z]+)*)?\s?(?:University|Hospital|Park|Center|Institute|School|Plaza|Building|Station)\b"
    )
    matches = list(re.finditer(location_pattern, text))
    for match in reversed(matches):
        start, end = match.span()
        text = text[:start] + block * (end - start) + text[end:]
        address_redaction_count += 1
    new_tokens = []
    new_spaces = []
    for token in doc:
        if token.idx < len(text):
            new_tokens.append(text[token.idx:token.idx + len(token.text)])
            new_spaces.append(token.whitespace_)
    redacted_doc = Doc(doc.vocab, words=new_tokens, spaces=new_spaces)
    redacted_doc._.redact_address_count = address_redaction_count
    return redacted_doc


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, action='append', help="Input file pattern eg: '*.txt' ")
    parser.add_argument("--names", action="store_true", help="To redact names")
    parser.add_argument("--dates", action="store_true", help="To redact dates")
    parser.add_argument("--phones", action="store_true", help="To redact phone numbers")
    parser.add_argument("--address", action="store_true", help="To redact addresses")
    parser.add_argument("--concept", action='append', help="concept to be redacted")
    parser.add_argument("--output", required=True, help="Output directory to store redacted files")
    parser.add_argument("--stats", help="Location to write the stats")

    args = parser.parse_args()

    write_stats_to = None
    censor_flags = []

    if args.names:
        censor_flags.append("names")
    if args.dates:
        censor_flags.append("dates")
    if args.phones:
        censor_flags.append("phones")
    if args.address:
        censor_flags.append("address")
    if args.stats:
        write_stats_to = args.stats

    main(args.input, censor_flags, args.concept, args.output, write_stats_to)


