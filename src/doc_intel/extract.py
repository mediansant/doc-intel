from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
from doc_intel.schema import ContractRecord

client = OpenAI()

MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """You are an expert legal data extraction assistant. Your task is to extract precise metadata and clause information from the provided contract markdown text according to the requested schema.

Guidelines:
1. Accuracy & Verbatim Evidence: Every extracted value must be backed by an exact, verbatim quote from the text in the corresponding evidence field. Do not paraphrase evidence quotes.
2. Boolean Clauses Handling: For boolean fields like 'cap_on_liability' and 'non_compete', if the contract does not address or contain the clause, set the value to `False` (and its evidence field to `null`). Only return `True` if explicitly present and supported by evidence.
3. Explicit Absence for Other Fields: If standard text/date/list fields are not present, set both the value field and its evidence field to null.
4. Normalization: Format dates strictly as YYYY-MM-DD. Provide jurisdiction names as bare place names.
"""

def extract(contract_md: str, model: str = MODEL) -> ContractRecord:
    completion = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user", 
                "content": f"<contract>\n{contract_md}\n</contract>\n\nExtract the record."
            },
        ],
        response_format=ContractRecord,
    )
    return completion.choices[0].message.parsed