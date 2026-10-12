from pydantic import BaseModel, Field

class ContractRecord(BaseModel):
    governing_law: str | None = Field(
        description="Jurisdiction whose law governs the contract, as a bare "
        "place name, e.g. 'Delaware'. Null if the contract does not state one."
    )
    governing_law_evidence: str | None = Field(
        description="Verbatim sentence from the contract supporting governing_law. "
        "Null if governing_law is null."
    )
    
    parties: list[str] | None = Field(
        description="List of the primary contracting entities/parties named in the preamble. "
        "Null if not specified."
    )
    parties_evidence: str | None = Field(
        description="Verbatim sentence from the contract supporting parties. "
        "Null if parties is null."
    )
    
    agreement_date: str | None = Field(
        description="The date the contract was executed or entered into, formatted strictly "
        "as ISO YYYY-MM-DD. Null if not specified."
    )
    agreement_date_evidence: str | None = Field(
        description="Verbatim sentence from the contract supporting agreement_date. "
        "Null if agreement_date is null."
    )
    
    renewal_term: str | None = Field(
        description="Free text describing the renewal term, automatic renewal, or extension provisions. "
        "Null if not specified."
    )
    renewal_term_evidence: str | None = Field(
        description="Verbatim sentence from the contract supporting renewal_term. "
        "Null if renewal_term is null."
    )
    
    cap_on_liability: bool = Field(
        description="True if the contract explicitly specifies a monetary cap or limit on liability. "
        "False if liability is expressly unlimited or if the topic is not addressed/absent."
    )
    cap_on_liability_evidence: str | None = Field(
        description="Verbatim sentence from the contract supporting cap_on_liability. "
        "Null if cap_on_liability is False due to absence."
    )
    
    non_compete: bool = Field(
        description="True if the contract contains a non-compete clause restricting a party from competing. "
        "False if explicitly absent or not addressed in the contract."
    )
    non_compete_evidence: str | None = Field(
        description="Verbatim sentence from the contract supporting non_compete. "
        "Null if non_compete is False due to absence."
    )