import os
import pytest
from redactor import *
from unittest.mock import patch


def test_redact_concepts():
    text = "This is a house. Pls do not enter."
    concept = ['house']
    actual_txt, actual_count = redact_concepts(text, concept)
    expected_txt, expected_count = "████████████████ Pls do not enter.", 1
    assert expected_txt == actual_txt
    assert expected_count == actual_count

def test_get_synonyms():
    actual = get_synonyms("house")
    assert "mansion" in actual

def test_download_nltk_resources():
    download_nltk_resources()
    assert 1 == 1

def test_redact_address():
    nlp = spacy.load("en_core_web_trf")
    nlp.add_pipe("redact_address")
    doc = nlp("123 Main Street")
    expected = "███ ████ ██████"
    assert expected == doc.text


def test_redact_phones():
    nlp = spacy.load("en_core_web_trf")
    nlp.add_pipe("redact_phones")
    doc = nlp("Number 1 : 333 333 9999 Number 2: 345-599-5995")
    expected = "Number 1 : ███ ███ ████ Number 2: ████████████"
    assert expected == doc.text


def test_redact_dates():
    nlp = spacy.load("en_core_web_trf")
    nlp.add_pipe("redact_dates")
    doc = nlp("Today date is 12/20/2011")
    expected = "Today date is ██████████"
    assert expected == doc.text


def test_redact_names():
    nlp = spacy.load("en_core_web_trf")
    nlp.add_pipe("redact_names")
    doc = nlp("I spoke with Emily from the PR team earlier today")
    expected = "I spoke with █████ from the PR team earlier today"
    assert expected == doc.text


def test_process_files():
    file = ['tests/file.txt']
    censor_flags = ["phones"]
    concept = ""
    output_dir = "tests/"
    actual = process_files(file, censor_flags, concept, output_dir)
    expected = [('file.txt', {'redacted phones': 2})]
    assert expected == actual


def test_redaction():
    txt = "Number 1 : 333 333 9999 Number 2: 345-599-5995"
    censor_flags = ["phones"]
    concept = ""
    x, y = redaction(txt, censor_flags, concept)
    expected_x = "Number 1 : ███ ███ ████ Number 2: ████████████"
    expected_y = {'redacted phones': 2}
    assert expected_x == x
    assert expected_y == y


def test_read_file():
    file = 'tests/file.txt'
    actual = read_file(file)
    expected = "Number 1 : 333 333 9999 Number 2: 345-599-5995"
    assert expected == actual


def test_get_files():
    with patch('glob.glob') as mock_glob:
        input = ['file.txt']
        mock_glob.return_value = ['file.txt']
        actual = get_files(input)
        expected = ['file.txt']
        assert actual == expected


def test_write_all_stats(capsys):
    all_stats = [('file.txt', {'redacted addresses': 0, 'redacted dates': 0, 'redacted names': 0, 'redacted phones': 2})]
    write_stats_to = 'stdout'
    expected = "       ********** Stats **********\nFile Name: file.txt \nTotal Redacted items: 2\n     Number of redacted addresses: 0\n     Number of redacted dates: 0\n     Number of redacted names: 0\n     Number of redacted phones: 2\n\nTotal redacted items across 1 files: 2\n"
    write_all_stats(all_stats, write_stats_to)
    captured = capsys.readouterr()
    assert expected in captured.out


def test_main(capsys):
    input = ["tests/file.txt"]
    censor_flags = ["phones"]
    concept = ""
    output = "tests/"
    write_stats_to = 'stdout'
    expected = "       ********** Stats **********\nFile Name: file.txt \nTotal Redacted items: 2\n"
    with patch('glob.glob') as mock_glob:
        mock_glob.return_value = ['tests/file.txt']
        main(input, censor_flags, concept, output, write_stats_to)
        captured = capsys.readouterr()
        assert expected in captured.out
