"""
Pydantic models for structured data extraction from SEC filings.

These schemas define the expected output format for financial data extraction,
ensuring consistent, validated, and type-safe data throughout the pipeline.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date
from enum import Enum


class FilingType(str, Enum):
    """SEC filing types supported by the system."""
    FORM_10K = "10-K"
    FORM_10Q = "10-Q"
    FORM_8K = "8-K"


class FinancialMetrics(BaseModel):
    """
    Core financial metrics extracted from SEC filings.

    All monetary values are in USD. Values are null if not found in the filing.
    This follows the "null over guess" principle - we never estimate values.
    """

    # Income Statement
    revenue: Optional[float] = Field(None, description="Total revenue in USD")
    cost_of_revenue: Optional[float] = Field(None, description="Cost of goods sold in USD")
    gross_profit: Optional[float] = Field(None, description="Gross profit in USD")
    operating_expenses: Optional[float] = Field(None, description="Total operating expenses in USD")
    operating_income: Optional[float] = Field(None, description="Operating income in USD")
    net_income: Optional[float] = Field(None, description="Net income in USD")
    eps_basic: Optional[float] = Field(None, description="Basic earnings per share")
    eps_diluted: Optional[float] = Field(None, description="Diluted earnings per share")

    # Balance Sheet
    total_assets: Optional[float] = Field(None, description="Total assets in USD")
    total_liabilities: Optional[float] = Field(None, description="Total liabilities in USD")
    total_equity: Optional[float] = Field(None, description="Total stockholders equity in USD")
    cash_and_equivalents: Optional[float] = Field(None, description="Cash and cash equivalents in USD")
    total_debt: Optional[float] = Field(None, description="Total debt (short + long term) in USD")

    # Cash Flow
    operating_cash_flow: Optional[float] = Field(None, description="Net cash from operating activities in USD")
    investing_cash_flow: Optional[float] = Field(None, description="Net cash from investing activities in USD")
    financing_cash_flow: Optional[float] = Field(None, description="Net cash from financing activities in USD")
    capital_expenditures: Optional[float] = Field(None, description="Capital expenditures in USD")
    free_cash_flow: Optional[float] = Field(None, description="Free cash flow (operating - capex) in USD")

    # Key Ratios (calculated or extracted)
    gross_margin: Optional[float] = Field(None, description="Gross profit margin as decimal")
    operating_margin: Optional[float] = Field(None, description="Operating margin as decimal")
    net_margin: Optional[float] = Field(None, description="Net profit margin as decimal")


class RiskFactor(BaseModel):
    """
    Individual risk factor extracted from SEC filing Item 1A.

    Risk factors are categorized and assessed for severity to enable
    tracking changes across filing periods.
    """

    category: str = Field(
        ...,
        description="Risk category: market, operational, regulatory, financial, legal, cybersecurity, competitive, macroeconomic, other"
    )
    title: str = Field(..., description="Brief risk title (1-2 sentences)")
    description: str = Field(..., description="Full risk description from filing")
    severity: str = Field(
        ...,
        description="Assessed severity: low, medium, high, critical"
    )
    is_new: bool = Field(
        False,
        description="Whether this risk is new compared to prior filing"
    )


class DocumentChunk(BaseModel):
    """
    A chunk of document text with metadata for vector storage.
    """

    id: str = Field(..., description="Unique chunk ID: {ticker}_{filing_type}_{date}_{section}_{chunk_num}")
    text: str = Field(..., description="The chunk text content")
    ticker: str = Field(..., description="Company ticker symbol")
    filing_type: str = Field(..., description="Filing type (10-K, 10-Q, 8-K)")
    filing_date: str = Field(..., description="Filing date in YYYY-MM-DD format")
    section: str = Field(..., description="SEC section (item_1, item_1a, item_7, item_8, etc.)")
    chunk_index: int = Field(..., description="Index of this chunk within the section")
    char_start: int = Field(..., description="Starting character position in original document")
    char_end: int = Field(..., description="Ending character position in original document")


class FilingMetadata(BaseModel):
    """
    Metadata about an SEC filing.
    """

    ticker: str = Field(..., description="Company ticker symbol")
    company_name: str = Field(..., description="Full company name")
    cik: str = Field(..., description="SEC Central Index Key")
    filing_type: FilingType
    filing_date: date
    accession_number: str = Field(..., description="SEC accession number")
    fiscal_year: int
    fiscal_quarter: Optional[int] = Field(None, description="Quarter for 10-Q filings (1-4)")
    fiscal_year_end: str = Field(..., description="Fiscal year end date (MM-DD)")
    document_url: str = Field(..., description="URL to the filing document")


class FilingExtraction(BaseModel):
    """
    Complete extraction from a single SEC filing.

    This is the primary output of the extraction pipeline, containing
    all structured data extracted from a filing along with metadata
    and validation status.
    """

    # Filing identification
    ticker: str
    company_name: str
    filing_type: FilingType
    filing_date: date
    fiscal_year: int
    fiscal_quarter: Optional[int] = None
    accession_number: str

    # Extracted data
    financial_metrics: FinancialMetrics
    risk_factors: List[RiskFactor] = Field(default_factory=list)
    business_summary: str = Field(..., max_length=3000, description="Summary of business description")

    # Extraction metadata
    extraction_timestamp: str = Field(..., description="ISO timestamp of extraction")
    model_used: str = Field(..., description="LLM model used for extraction")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Overall extraction confidence")

    # Validation status
    validation_status: str = Field(
        "pending",
        description="Validation status: pending, passed, failed, manual_review"
    )
    validation_errors: List[str] = Field(default_factory=list)
    validation_warnings: List[str] = Field(default_factory=list)


class ExtractionValidation(BaseModel):
    """
    Validation results for a FilingExtraction.
    """

    is_valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    # Specific validation checks
    required_fields_present: bool = Field(..., description="All mandatory fields extracted")
    balance_sheet_balances: bool = Field(..., description="Assets ≈ Liabilities + Equity")
    margins_consistent: bool = Field(..., description="Profit margins are mathematically consistent")
    values_in_range: bool = Field(..., description="Values within reasonable ranges for company size")
    dates_consistent: bool = Field(..., description="Dates are internally consistent")


class RAGResponse(BaseModel):
    """
    Response from the RAG query pipeline.
    """

    query: str = Field(..., description="Original user query")
    answer: str = Field(..., description="Generated answer with inline citations [1], [2], etc.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the answer")

    citations: List[dict] = Field(
        default_factory=list,
        description="List of citations with 'text', 'source', 'relevance' keys"
    )

    # Query metadata
    chunks_retrieved: int = Field(..., description="Number of chunks retrieved")
    chunks_used: int = Field(..., description="Number of chunks used in context")
    model_used: str = Field(..., description="LLM model used for generation")
