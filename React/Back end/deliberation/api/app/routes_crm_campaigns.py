"""
CRM – campaign CRUD, contributions, milestones, expenses, proof,
partners, volunteers, analysis, deliberation launch, admin campaign endpoints.
"""
from typing import List, Optional, Tuple
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .db import get_driver
from .routes import create_conversation, seed_comments
from .schemas import ConversationCreate, SeedCommentsRequest
from .routes_crm_helpers import (
    CAMPAIGN_STATUSES,
    PAYMENT_STATUSES,
    TASK_STATUSES,
    ENABLE_PAYMENTS,
    MAX_CONTRIBUTION_AMOUNT,
    _clean_text,
    _safe_float,
    _execute_read,
    _execute_write,
    _db_session,
    _query_df,
    _compute_campaign_budget,
    _generate_campaign_analysis,
    _prepare_seed_statements,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CampaignCreate(BaseModel):
    name: str
    topic: Optional[str] = ""
    objective: Optional[str] = ""
    problemTitle: Optional[str] = ""
    problemDescription: Optional[str] = ""
    locationCity: Optional[str] = ""
    locationDistrict: Optional[str] = ""
    beneficiaryType: Optional[str] = ""
    fundingTargetAmount: Optional[float] = 0
    currency: Optional[str] = "GEL"
    fundsRaisedAmount: Optional[float] = 0
    operationalFeePercent: Optional[float] = 0
    operationalFeeAmount: Optional[float] = 0
    executionBudgetAmount: Optional[float] = 0
    campaignVisibility: Optional[str] = "Public"
    campaignCategory: Optional[str] = ""
    riskLevel: Optional[str] = ""
    implementationSteps: Optional[str] = ""
    responsibleOwner: Optional[str] = ""
    communityPartner: Optional[str] = ""
    executionStartDate: Optional[str] = ""
    expectedCompletionDate: Optional[str] = ""
    legislationText: Optional[str] = ""
    manifestoText: Optional[str] = ""
    expertPrompt: Optional[str] = ""
    status: Optional[str] = "Planned"
    startDate: Optional[str] = ""
    endDate: Optional[str] = ""
    owner: Optional[str] = ""
    targetGroup: Optional[str] = ""
    goal: Optional[int] = 0
    notes: Optional[str] = ""


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    topic: Optional[str] = None
    objective: Optional[str] = None
    problemTitle: Optional[str] = None
    problemDescription: Optional[str] = None
    locationCity: Optional[str] = None
    locationDistrict: Optional[str] = None
    beneficiaryType: Optional[str] = None
    fundingTargetAmount: Optional[float] = None
    currency: Optional[str] = None
    fundsRaisedAmount: Optional[float] = None
    operationalFeePercent: Optional[float] = None
    operationalFeeAmount: Optional[float] = None
    executionBudgetAmount: Optional[float] = None
    campaignVisibility: Optional[str] = None
    campaignCategory: Optional[str] = None
    riskLevel: Optional[str] = None
    implementationSteps: Optional[str] = None
    responsibleOwner: Optional[str] = None
    communityPartner: Optional[str] = None
    executionStartDate: Optional[str] = None
    expectedCompletionDate: Optional[str] = None
    legislationText: Optional[str] = None
    manifestoText: Optional[str] = None
    expertPrompt: Optional[str] = None
    status: Optional[str] = None
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    owner: Optional[str] = None
    targetGroup: Optional[str] = None
    goal: Optional[int] = None
    notes: Optional[str] = None


class CampaignOut(BaseModel):
    campaign_id: str = Field(alias="campaignId")
    name: str
    topic: Optional[str] = ""
    objective: Optional[str] = ""
    problem_title: Optional[str] = Field(alias="problemTitle", default="")
    problem_description: Optional[str] = Field(alias="problemDescription", default="")
    location_city: Optional[str] = Field(alias="locationCity", default="")
    location_district: Optional[str] = Field(alias="locationDistrict", default="")
    beneficiary_type: Optional[str] = Field(alias="beneficiaryType", default="")
    funding_target_amount: float = Field(alias="fundingTargetAmount", default=0)
    currency: str = "GEL"
    funds_raised_amount: float = Field(alias="fundsRaisedAmount", default=0)
    operational_fee_percent: float = Field(alias="operationalFeePercent", default=0)
    operational_fee_amount: float = Field(alias="operationalFeeAmount", default=0)
    execution_budget_amount: float = Field(alias="executionBudgetAmount", default=0)
    campaign_visibility: Optional[str] = Field(alias="campaignVisibility", default="Public")
    campaign_category: Optional[str] = Field(alias="campaignCategory", default="")
    risk_level: Optional[str] = Field(alias="riskLevel", default="")
    implementation_steps: Optional[str] = Field(alias="implementationSteps", default="")
    responsible_owner: Optional[str] = Field(alias="responsibleOwner", default="")
    community_partner: Optional[str] = Field(alias="communityPartner", default="")
    execution_start_date: Optional[str] = Field(alias="executionStartDate", default="")
    expected_completion_date: Optional[str] = Field(
        alias="expectedCompletionDate", default=""
    )
    status: str
    start_date: Optional[str] = Field(alias="startDate", default="")
    end_date: Optional[str] = Field(alias="endDate", default="")
    owner: Optional[str] = ""
    target_group: Optional[str] = Field(alias="targetGroup", default="")
    goal: int = 0
    notes: Optional[str] = ""
    legislation_text: Optional[str] = Field(alias="legislationText", default="")
    manifesto_text: Optional[str] = Field(alias="manifestoText", default="")
    expert_prompt: Optional[str] = Field(alias="expertPrompt", default="")
    consensus_statements: List[str] = Field(alias="consensusStatements", default_factory=list)
    polarization_statements: List[str] = Field(
        alias="polarizationStatements", default_factory=list
    )
    deliberation_conversation_id: Optional[str] = Field(
        alias="deliberationConversationId", default=""
    )


class CampaignAnalysisRequest(BaseModel):
    topic: Optional[str] = ""
    legislationText: Optional[str] = ""
    manifestoText: Optional[str] = ""
    expertPrompt: Optional[str] = ""


class CampaignContributionCreate(BaseModel):
    amount: float
    currency: Optional[str] = "GEL"
    contributorName: Optional[str] = ""
    contributorEmail: Optional[str] = ""
    paymentStatus: Optional[str] = "succeeded"
    isAnonymous: Optional[bool] = False
    donorVisibility: Optional[str] = "public"
    termsAccepted: Optional[bool] = True
    privacyAccepted: Optional[bool] = True
    note: Optional[str] = ""


class CampaignContributionOut(BaseModel):
    contribution_id: str = Field(alias="contributionId")
    campaign_id: str = Field(alias="campaignId")
    amount: float
    currency: str
    operational_share_amount: float = Field(alias="operationalShareAmount", default=0)
    execution_share_amount: float = Field(alias="executionShareAmount", default=0)
    contributor_name: Optional[str] = Field(alias="contributorName", default="")
    contributor_email: Optional[str] = Field(alias="contributorEmail", default="")
    payment_status: str = Field(alias="paymentStatus", default="succeeded")
    is_anonymous: bool = Field(alias="isAnonymous", default=False)
    donor_visibility: Optional[str] = Field(alias="donorVisibility", default="public")
    terms_accepted: bool = Field(alias="termsAccepted", default=True)
    privacy_accepted: bool = Field(alias="privacyAccepted", default=True)
    note: Optional[str] = ""
    created_at: Optional[str] = Field(alias="createdAt", default=None)


class CampaignCheckoutRequest(BaseModel):
    amount: float
    currency: Optional[str] = "GEL"
    contributorName: Optional[str] = ""
    contributorEmail: Optional[str] = ""
    isAnonymous: Optional[bool] = False
    donorVisibility: Optional[str] = "public"
    termsAccepted: Optional[bool] = False
    privacyAccepted: Optional[bool] = False
    note: Optional[str] = ""
    paymentMethod: Optional[str] = "card"


class CampaignCheckoutOut(BaseModel):
    checkout_id: str = Field(alias="checkoutId")
    contribution_id: str = Field(alias="contributionId")
    campaign_id: str = Field(alias="campaignId")
    amount: float
    currency: str
    payment_status: str = Field(alias="paymentStatus")
    payment_url: Optional[str] = Field(alias="paymentUrl", default="")


class PaymentWebhookEvent(BaseModel):
    campaignId: str
    contributionId: str
    paymentStatus: str
    processorRef: Optional[str] = ""
    eventId: Optional[str] = ""


class CampaignFundingSummaryOut(BaseModel):
    campaign_id: str = Field(alias="campaignId")
    funding_target_amount: float = Field(alias="fundingTargetAmount")
    funds_raised_amount: float = Field(alias="fundsRaisedAmount")
    currency: str
    operational_fee_percent: float = Field(alias="operationalFeePercent")
    operational_fee_amount: float = Field(alias="operationalFeeAmount")
    execution_budget_amount: float = Field(alias="executionBudgetAmount")
    contributor_count: int = Field(alias="contributorCount")
    allocated_operations: float = Field(alias="allocatedOperations")
    allocated_execution: float = Field(alias="allocatedExecution")


class CampaignMilestoneCreate(BaseModel):
    title: str
    amountTarget: Optional[float] = 0
    dueDate: Optional[str] = ""
    status: Optional[str] = "Planned"
    completionPercent: Optional[float] = 0


class CampaignMilestoneOut(BaseModel):
    milestone_id: str = Field(alias="milestoneId")
    campaign_id: str = Field(alias="campaignId")
    title: str
    amount_target: float = Field(alias="amountTarget", default=0)
    due_date: Optional[str] = Field(alias="dueDate", default="")
    status: str
    completion_percent: float = Field(alias="completionPercent", default=0)
    created_at: Optional[str] = Field(alias="createdAt", default=None)
    updated_at: Optional[str] = Field(alias="updatedAt", default=None)


class CampaignExpenseCreate(BaseModel):
    category: str
    vendor: Optional[str] = ""
    amount: float
    currency: Optional[str] = "GEL"
    receiptLink: Optional[str] = ""
    approvedBy: Optional[str] = ""
    approvalStatus: Optional[str] = "Pending"
    milestoneId: Optional[str] = ""


class CampaignExpenseOut(BaseModel):
    expense_id: str = Field(alias="expenseId")
    campaign_id: str = Field(alias="campaignId")
    category: str
    vendor: Optional[str] = ""
    amount: float
    currency: str
    receipt_link: Optional[str] = Field(alias="receiptLink", default="")
    approved_by: Optional[str] = Field(alias="approvedBy", default="")
    approval_status: Optional[str] = Field(alias="approvalStatus", default="Pending")
    milestone_id: Optional[str] = Field(alias="milestoneId", default="")
    created_at: Optional[str] = Field(alias="createdAt", default=None)


class CampaignProofCreate(BaseModel):
    artifactType: str
    caption: Optional[str] = ""
    url: str
    uploadedBy: Optional[str] = ""
    verificationStatus: Optional[str] = "Pending"
    milestoneId: Optional[str] = ""


class CampaignProofOut(BaseModel):
    proof_id: str = Field(alias="proofId")
    campaign_id: str = Field(alias="campaignId")
    artifact_type: str = Field(alias="artifactType")
    caption: Optional[str] = ""
    url: str
    uploaded_by: Optional[str] = Field(alias="uploadedBy", default="")
    verification_status: str = Field(alias="verificationStatus", default="Pending")
    milestone_id: Optional[str] = Field(alias="milestoneId", default="")
    created_at: Optional[str] = Field(alias="createdAt", default=None)


class CampaignPartnerCreate(BaseModel):
    name: str
    role: Optional[str] = ""
    contact: Optional[str] = ""
    verificationNotes: Optional[str] = ""


class CampaignPartnerOut(BaseModel):
    partner_id: str = Field(alias="partnerId")
    campaign_id: str = Field(alias="campaignId")
    name: str
    role: Optional[str] = ""
    contact: Optional[str] = ""
    verification_notes: Optional[str] = Field(alias="verificationNotes", default="")
    created_at: Optional[str] = Field(alias="createdAt", default=None)


class CampaignUpdateCreate(BaseModel):
    message: str
    createdBy: Optional[str] = ""
    status: Optional[str] = ""


class CampaignUpdateOut(BaseModel):
    update_id: str = Field(alias="updateId")
    campaign_id: str = Field(alias="campaignId")
    message: str
    created_by: Optional[str] = Field(alias="createdBy", default="")
    status: Optional[str] = ""
    created_at: Optional[str] = Field(alias="createdAt", default=None)


class CampaignMessageCreate(BaseModel):
    channel: Optional[str] = "whatsapp"
    language: Optional[str] = "ka"
    tone: Optional[str] = "clear"
    title: Optional[str] = ""
    body: str
    callToAction: Optional[str] = ""
    status: Optional[str] = "Draft"
    segmentId: Optional[str] = ""
    generatedByAi: Optional[bool] = False
    promptContext: Optional[str] = ""


class CampaignMessageUpdate(BaseModel):
    channel: Optional[str] = None
    language: Optional[str] = None
    tone: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    callToAction: Optional[str] = None
    status: Optional[str] = None
    segmentId: Optional[str] = None
    generatedByAi: Optional[bool] = None
    promptContext: Optional[str] = None


class CampaignMessageGenerateRequest(BaseModel):
    channel: Optional[str] = "whatsapp"
    language: Optional[str] = "ka"
    tone: Optional[str] = "clear"
    instructions: Optional[str] = ""


class CampaignMessageOut(BaseModel):
    message_id: str = Field(alias="messageId")
    campaign_id: str = Field(alias="campaignId")
    channel: str
    language: str
    tone: str
    title: Optional[str] = ""
    body: str
    call_to_action: Optional[str] = Field(alias="callToAction", default="")
    status: str
    segment_id: Optional[str] = Field(alias="segmentId", default="")
    generated_by_ai: bool = Field(alias="generatedByAi", default=False)
    prompt_context: Optional[str] = Field(alias="promptContext", default="")
    created_at: Optional[str] = Field(alias="createdAt", default=None)
    updated_at: Optional[str] = Field(alias="updatedAt", default=None)


class CampaignMessageSuggestionsOut(BaseModel):
    messages: List[CampaignMessageCreate]


class CampaignTaskCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    status: Optional[str] = "Open"
    dueDate: Optional[str] = ""
    assigneeEmail: Optional[str] = ""
    milestoneId: Optional[str] = ""


class CampaignTaskOut(BaseModel):
    task_id: str = Field(alias="taskId")
    campaign_id: str = Field(alias="campaignId")
    milestone_id: Optional[str] = Field(alias="milestoneId", default="")
    title: str
    description: Optional[str] = ""
    status: str
    due_date: Optional[str] = Field(alias="dueDate", default="")
    assignee_email: Optional[str] = Field(alias="assigneeEmail", default="")
    assignee_name: Optional[str] = Field(alias="assigneeName", default="")
    created_at: Optional[str] = Field(alias="createdAt", default=None)
    updated_at: Optional[str] = Field(alias="updatedAt", default=None)


class CampaignTransparencyOut(BaseModel):
    campaign_id: str = Field(alias="campaignId")
    funding_target_amount: float = Field(alias="fundingTargetAmount")
    funds_raised_amount: float = Field(alias="fundsRaisedAmount")
    amount_spent: float = Field(alias="amountSpent")
    operational_fee_amount: float = Field(alias="operationalFeeAmount")
    execution_budget_amount: float = Field(alias="executionBudgetAmount")
    remaining_balance: float = Field(alias="remainingBalance")
    expense_count: int = Field(alias="expenseCount")
    proof_count: int = Field(alias="proofCount")


class CampaignAuditEventOut(BaseModel):
    event_type: str = Field(alias="eventType")
    summary: str
    created_at: Optional[str] = Field(alias="createdAt", default=None)


class CampaignVolunteerCreate(BaseModel):
    name: str
    email: Optional[str] = ""
    phone: Optional[str] = ""
    role: Optional[str] = ""
    notes: Optional[str] = ""


class CampaignVolunteerOut(BaseModel):
    volunteer_id: str = Field(alias="volunteerId")
    campaign_id: str = Field(alias="campaignId")
    name: str
    email: Optional[str] = ""
    phone: Optional[str] = ""
    role: Optional[str] = ""
    notes: Optional[str] = ""
    created_at: Optional[str] = Field(alias="createdAt", default=None)


class AdminContributionOut(BaseModel):
    contribution_id: str = Field(alias="contributionId")
    campaign_id: str = Field(alias="campaignId")
    campaign_name: str = Field(alias="campaignName")
    amount: float
    currency: str
    payment_status: str = Field(alias="paymentStatus")
    operational_share_amount: float = Field(alias="operationalShareAmount", default=0)
    execution_share_amount: float = Field(alias="executionShareAmount", default=0)
    contributor_name: Optional[str] = Field(alias="contributorName", default="")
    contributor_email: Optional[str] = Field(alias="contributorEmail", default="")
    created_at: Optional[str] = Field(alias="createdAt", default=None)


class ProofStatusUpdate(BaseModel):
    verificationStatus: str


class ExpenseApprovalUpdate(BaseModel):
    approvalStatus: str
    approvedBy: Optional[str] = ""


# ---------------------------------------------------------------------------
# Shared Cypher fragment for returning a full campaign row
# ---------------------------------------------------------------------------

_CAMPAIGN_RETURN = """
  c.campaignId AS campaignId,
  c.name AS name,
  coalesce(c.topic, '') AS topic,
  coalesce(c.objective, '') AS objective,
  coalesce(c.problemTitle, '') AS problemTitle,
  coalesce(c.problemDescription, '') AS problemDescription,
  coalesce(c.locationCity, '') AS locationCity,
  coalesce(c.locationDistrict, '') AS locationDistrict,
  coalesce(c.beneficiaryType, '') AS beneficiaryType,
  coalesce(c.fundingTargetAmount, 0) AS fundingTargetAmount,
  coalesce(c.currency, 'GEL') AS currency,
  coalesce(c.fundsRaisedAmount, 0) AS fundsRaisedAmount,
  coalesce(c.operationalFeePercent, 0) AS operationalFeePercent,
  coalesce(c.operationalFeeAmount, 0) AS operationalFeeAmount,
  coalesce(c.executionBudgetAmount, 0) AS executionBudgetAmount,
  coalesce(c.campaignVisibility, 'Public') AS campaignVisibility,
  coalesce(c.campaignCategory, '') AS campaignCategory,
  coalesce(c.riskLevel, '') AS riskLevel,
  coalesce(c.implementationSteps, '') AS implementationSteps,
  coalesce(c.responsibleOwner, '') AS responsibleOwner,
  coalesce(c.communityPartner, '') AS communityPartner,
  coalesce(c.executionStartDate, '') AS executionStartDate,
  coalesce(c.expectedCompletionDate, '') AS expectedCompletionDate,
  coalesce(c.status, 'Planned') AS status,
  coalesce(c.startDate, '') AS startDate,
  coalesce(c.endDate, '') AS endDate,
  coalesce(c.owner, '') AS owner,
  coalesce(c.targetGroup, '') AS targetGroup,
  coalesce(c.goal, 0) AS goal,
  coalesce(c.notes, '') AS notes,
  coalesce(c.legislationText, '') AS legislationText,
  coalesce(c.manifestoText, '') AS manifestoText,
  coalesce(c.expertPrompt, '') AS expertPrompt,
  coalesce(c.consensusStatements, []) AS consensusStatements,
  coalesce(c.polarizationStatements, []) AS polarizationStatements,
  coalesce(c.deliberationConversationId, '') AS deliberationConversationId
"""


# ---------------------------------------------------------------------------
# Campaign CRUD
# ---------------------------------------------------------------------------

@router.get("/campaigns", response_model=List[CampaignOut])
def list_campaigns(limit: int = Query(200, ge=10, le=1000)):
    df = _query_df(
        f"""
        MATCH (c:Campaign)
        RETURN
          {_CAMPAIGN_RETURN}
        ORDER BY c.createdAt DESC
        LIMIT $limit
        """,
        {"limit": int(limit)},
    )
    return df.to_dict(orient="records") if not df.empty else []


@router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
def get_campaign(campaign_id: str):
    df = _query_df(
        f"""
        MATCH (c:Campaign {{campaignId: $campaignId}})
        RETURN
          {_CAMPAIGN_RETURN}
        LIMIT 1
        """,
        {"campaignId": _clean_text(campaign_id)},
    )
    if df.empty:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return df.iloc[0].to_dict()


@router.patch("/campaigns/{campaign_id}", response_model=CampaignOut)
def update_campaign(campaign_id: str, payload: CampaignUpdate):
    campaign_id = _clean_text(campaign_id)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    df = _query_df(
        f"""
        MATCH (c:Campaign {{campaignId: $campaignId}})
        RETURN
          {_CAMPAIGN_RETURN}
        LIMIT 1
        """,
        {"campaignId": campaign_id},
    )
    if df.empty:
        raise HTTPException(status_code=404, detail="Campaign not found")
    existing = df.iloc[0].to_dict()
    status = _clean_text(payload.status) if payload.status is not None else existing.get("status")
    if status and status not in CAMPAIGN_STATUSES:
        status = existing.get("status") or "Planned"
    target_amount = (
        _safe_float(payload.fundingTargetAmount, None)
        if payload.fundingTargetAmount is not None
        else _safe_float(existing.get("fundingTargetAmount"), 0.0)
    )
    fee_percent = (
        _safe_float(payload.operationalFeePercent, None)
        if payload.operationalFeePercent is not None
        else _safe_float(existing.get("operationalFeePercent"), 0.0)
    )
    fee_amount = (
        _safe_float(payload.operationalFeeAmount, None)
        if payload.operationalFeeAmount is not None
        else _safe_float(existing.get("operationalFeeAmount"), 0.0)
    )
    execution_amount = (
        _safe_float(payload.executionBudgetAmount, None)
        if payload.executionBudgetAmount is not None
        else _safe_float(existing.get("executionBudgetAmount"), 0.0)
    )
    fee_percent, fee_amount, execution_amount = _compute_campaign_budget(
        target_amount, fee_percent, fee_amount, execution_amount
    )
    funds_raised = (
        _safe_float(payload.fundsRaisedAmount, None)
        if payload.fundsRaisedAmount is not None
        else _safe_float(existing.get("fundsRaisedAmount"), 0.0)
    )
    if status == "Funded" and target_amount and funds_raised < target_amount:
        raise HTTPException(
            status_code=400,
            detail="Campaign cannot move to Funded before reaching the target.",
        )
    if status in {"Awaiting Verification", "Completed"}:
        proof_df = _query_df(
            """
            MATCH (c:Campaign {campaignId: $campaignId})-[:HAS_PROOF]->(p:CampaignProof)
            RETURN
              count(p) AS proofCount,
              sum(CASE WHEN coalesce(p.verificationStatus, '') = 'Verified' THEN 1 ELSE 0 END) AS verifiedCount
            """,
            {"campaignId": campaign_id},
        )
        proof_count = int((proof_df.iloc[0].get("proofCount") if not proof_df.empty else 0) or 0)
        verified_count = int((proof_df.iloc[0].get("verifiedCount") if not proof_df.empty else 0) or 0)
        if status == "Awaiting Verification" and proof_count == 0:
            raise HTTPException(
                status_code=400,
                detail="Campaign needs proof artifacts before verification.",
            )
        if status == "Completed" and verified_count == 0:
            raise HTTPException(
                status_code=400,
                detail="Campaign needs verified proof before completion.",
            )
    updated = {
        "name": _clean_text(payload.name) if payload.name is not None else existing.get("name"),
        "topic": _clean_text(payload.topic) if payload.topic is not None else existing.get("topic"),
        "objective": _clean_text(payload.objective) if payload.objective is not None else existing.get("objective"),
        "problemTitle": _clean_text(payload.problemTitle) if payload.problemTitle is not None else existing.get("problemTitle"),
        "problemDescription": _clean_text(payload.problemDescription)
        if payload.problemDescription is not None
        else existing.get("problemDescription"),
        "locationCity": _clean_text(payload.locationCity)
        if payload.locationCity is not None
        else existing.get("locationCity"),
        "locationDistrict": _clean_text(payload.locationDistrict)
        if payload.locationDistrict is not None
        else existing.get("locationDistrict"),
        "beneficiaryType": _clean_text(payload.beneficiaryType)
        if payload.beneficiaryType is not None
        else existing.get("beneficiaryType"),
        "fundingTargetAmount": target_amount,
        "currency": _clean_text(payload.currency)
        if payload.currency is not None
        else existing.get("currency") or "GEL",
        "fundsRaisedAmount": funds_raised,
        "operationalFeePercent": fee_percent,
        "operationalFeeAmount": fee_amount,
        "executionBudgetAmount": execution_amount,
        "campaignVisibility": _clean_text(payload.campaignVisibility)
        if payload.campaignVisibility is not None
        else existing.get("campaignVisibility") or "Public",
        "campaignCategory": _clean_text(payload.campaignCategory)
        if payload.campaignCategory is not None
        else existing.get("campaignCategory"),
        "riskLevel": _clean_text(payload.riskLevel)
        if payload.riskLevel is not None
        else existing.get("riskLevel"),
        "implementationSteps": _clean_text(payload.implementationSteps)
        if payload.implementationSteps is not None
        else existing.get("implementationSteps"),
        "responsibleOwner": _clean_text(payload.responsibleOwner)
        if payload.responsibleOwner is not None
        else existing.get("responsibleOwner"),
        "communityPartner": _clean_text(payload.communityPartner)
        if payload.communityPartner is not None
        else existing.get("communityPartner"),
        "executionStartDate": _clean_text(payload.executionStartDate)
        if payload.executionStartDate is not None
        else existing.get("executionStartDate"),
        "expectedCompletionDate": _clean_text(payload.expectedCompletionDate)
        if payload.expectedCompletionDate is not None
        else existing.get("expectedCompletionDate"),
        "legislationText": _clean_text(payload.legislationText)
        if payload.legislationText is not None
        else existing.get("legislationText"),
        "manifestoText": _clean_text(payload.manifestoText)
        if payload.manifestoText is not None
        else existing.get("manifestoText"),
        "expertPrompt": _clean_text(payload.expertPrompt)
        if payload.expertPrompt is not None
        else existing.get("expertPrompt"),
        "status": status or existing.get("status") or "Planned",
        "startDate": _clean_text(payload.startDate)
        if payload.startDate is not None
        else existing.get("startDate"),
        "endDate": _clean_text(payload.endDate)
        if payload.endDate is not None
        else existing.get("endDate"),
        "owner": _clean_text(payload.owner) if payload.owner is not None else existing.get("owner"),
        "targetGroup": _clean_text(payload.targetGroup)
        if payload.targetGroup is not None
        else existing.get("targetGroup"),
        "goal": payload.goal if payload.goal is not None else existing.get("goal"),
        "notes": _clean_text(payload.notes) if payload.notes is not None else existing.get("notes"),
    }
    query = f"""
    MATCH (c:Campaign {{campaignId: $campaignId}})
    SET c.name = $name,
        c.topic = $topic,
        c.objective = $objective,
        c.problemTitle = $problemTitle,
        c.problemDescription = $problemDescription,
        c.locationCity = $locationCity,
        c.locationDistrict = $locationDistrict,
        c.beneficiaryType = $beneficiaryType,
        c.fundingTargetAmount = $fundingTargetAmount,
        c.currency = $currency,
        c.fundsRaisedAmount = $fundsRaisedAmount,
        c.operationalFeePercent = $operationalFeePercent,
        c.operationalFeeAmount = $operationalFeeAmount,
        c.executionBudgetAmount = $executionBudgetAmount,
        c.campaignVisibility = $campaignVisibility,
        c.campaignCategory = $campaignCategory,
        c.riskLevel = $riskLevel,
        c.implementationSteps = $implementationSteps,
        c.responsibleOwner = $responsibleOwner,
        c.communityPartner = $communityPartner,
        c.executionStartDate = $executionStartDate,
        c.expectedCompletionDate = $expectedCompletionDate,
        c.legislationText = $legislationText,
        c.manifestoText = $manifestoText,
        c.expertPrompt = $expertPrompt,
        c.status = $status,
        c.startDate = $startDate,
        c.endDate = $endDate,
        c.owner = $owner,
        c.targetGroup = $targetGroup,
        c.goal = $goal,
        c.notes = $notes,
        c.updatedAt = datetime()
    RETURN
      {_CAMPAIGN_RETURN}
    """
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(session, query, {"campaignId": campaign_id, **updated})
    if not records:
        raise HTTPException(status_code=500, detail="Campaign could not be updated")
    return records[0].data()


@router.post("/campaigns", response_model=CampaignOut)
def create_campaign(payload: CampaignCreate):
    name = _clean_text(payload.name)
    if not name:
        raise HTTPException(status_code=400, detail="Campaign name is required")
    status = _clean_text(payload.status) or "Planned"
    if status not in CAMPAIGN_STATUSES:
        status = "Planned"
    fee_percent, fee_amount, execution_amount = _compute_campaign_budget(
        payload.fundingTargetAmount,
        payload.operationalFeePercent,
        payload.operationalFeeAmount,
        payload.executionBudgetAmount,
    )
    campaign_id = str(uuid4())
    query = f"""
    CREATE (c:Campaign {{
      campaignId: $campaignId,
      name: $name,
      topic: $topic,
      objective: $objective,
      problemTitle: $problemTitle,
      problemDescription: $problemDescription,
      locationCity: $locationCity,
      locationDistrict: $locationDistrict,
      beneficiaryType: $beneficiaryType,
      fundingTargetAmount: $fundingTargetAmount,
      currency: $currency,
      fundsRaisedAmount: $fundsRaisedAmount,
      operationalFeePercent: $operationalFeePercent,
      operationalFeeAmount: $operationalFeeAmount,
      executionBudgetAmount: $executionBudgetAmount,
      campaignVisibility: $campaignVisibility,
      campaignCategory: $campaignCategory,
      riskLevel: $riskLevel,
      implementationSteps: $implementationSteps,
      responsibleOwner: $responsibleOwner,
      communityPartner: $communityPartner,
      executionStartDate: $executionStartDate,
      expectedCompletionDate: $expectedCompletionDate,
      status: $status,
      startDate: $startDate,
      endDate: $endDate,
      owner: $owner,
      targetGroup: $targetGroup,
      goal: $goal,
      notes: $notes,
      legislationText: $legislationText,
      manifestoText: $manifestoText,
      expertPrompt: $expertPrompt,
      consensusStatements: $consensusStatements,
      polarizationStatements: $polarizationStatements,
      deliberationConversationId: $deliberationConversationId,
      createdAt: datetime(),
      updatedAt: datetime()
    }})
    RETURN
      {_CAMPAIGN_RETURN}
    """
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "campaignId": campaign_id,
                "name": name,
                "topic": _clean_text(payload.topic),
                "objective": _clean_text(payload.objective),
                "problemTitle": _clean_text(payload.problemTitle),
                "problemDescription": _clean_text(payload.problemDescription),
                "locationCity": _clean_text(payload.locationCity),
                "locationDistrict": _clean_text(payload.locationDistrict),
                "beneficiaryType": _clean_text(payload.beneficiaryType),
                "fundingTargetAmount": _safe_float(payload.fundingTargetAmount, 0.0),
                "currency": _clean_text(payload.currency) or "GEL",
                "fundsRaisedAmount": _safe_float(payload.fundsRaisedAmount, 0.0),
                "operationalFeePercent": fee_percent,
                "operationalFeeAmount": fee_amount,
                "executionBudgetAmount": execution_amount,
                "campaignVisibility": _clean_text(payload.campaignVisibility) or "Public",
                "campaignCategory": _clean_text(payload.campaignCategory),
                "riskLevel": _clean_text(payload.riskLevel),
                "implementationSteps": _clean_text(payload.implementationSteps),
                "responsibleOwner": _clean_text(payload.responsibleOwner),
                "communityPartner": _clean_text(payload.communityPartner),
                "executionStartDate": _clean_text(payload.executionStartDate),
                "expectedCompletionDate": _clean_text(payload.expectedCompletionDate),
                "status": status,
                "startDate": _clean_text(payload.startDate),
                "endDate": _clean_text(payload.endDate),
                "owner": _clean_text(payload.owner),
                "targetGroup": _clean_text(payload.targetGroup),
                "goal": payload.goal or 0,
                "notes": _clean_text(payload.notes),
                "legislationText": _clean_text(payload.legislationText),
                "manifestoText": _clean_text(payload.manifestoText),
                "expertPrompt": _clean_text(payload.expertPrompt),
                "consensusStatements": [],
                "polarizationStatements": [],
                "deliberationConversationId": "",
            },
        )
    if not records:
        raise HTTPException(status_code=500, detail="Campaign could not be created")
    return records[0].data()


@router.delete("/campaigns/{campaign_id}")
def delete_campaign(campaign_id: str):
    campaign_id = _clean_text(campaign_id)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            "MATCH (c:Campaign {campaignId: $campaignId}) DETACH DELETE c",
            {"campaignId": campaign_id},
        )
    return {"deleted": True, "campaign_id": campaign_id}


# ---------------------------------------------------------------------------
# Contributions
# ---------------------------------------------------------------------------

@router.post(
    "/campaigns/{campaign_id}/contributions",
    response_model=CampaignContributionOut,
)
def create_campaign_contribution(campaign_id: str, payload: CampaignContributionCreate):
    campaign_id = _clean_text(campaign_id)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    amount = _safe_float(payload.amount, 0.0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Contribution amount must be positive")
    if MAX_CONTRIBUTION_AMOUNT > 0 and amount > MAX_CONTRIBUTION_AMOUNT:
        raise HTTPException(status_code=400, detail="Contribution amount exceeds limit")
    contribution_id = str(uuid4())
    payment_status = _clean_text(payload.paymentStatus) or "succeeded"
    if payment_status not in PAYMENT_STATUSES:
        payment_status = "succeeded"
    query = """
    MATCH (c:Campaign {campaignId: $campaignId})
    WITH c, $amount AS amount, coalesce(c.operationalFeePercent, 0) AS feePercent
    WITH c,
      amount,
      feePercent,
      round(amount * (feePercent / 100.0), 2) AS operationalShareAmount,
      amount - round(amount * (feePercent / 100.0), 2) AS executionShareAmount
    CREATE (contrib:CampaignContribution {
      contributionId: $contributionId,
      campaignId: $campaignId,
      amount: amount,
      currency: $currency,
      operationalShareAmount: operationalShareAmount,
      executionShareAmount: executionShareAmount,
      contributorName: $contributorName,
      contributorEmail: $contributorEmail,
      paymentStatus: $paymentStatus,
      isAnonymous: $isAnonymous,
      donorVisibility: $donorVisibility,
      termsAccepted: $termsAccepted,
      privacyAccepted: $privacyAccepted,
      note: $note,
      createdAt: datetime()
    })
    CREATE (c)-[:HAS_CONTRIBUTION]->(contrib)
    WITH c, contrib
    OPTIONAL MATCH (p:Person {email: $contributorEmail})
    FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END |
      MERGE (p)-[:CONTRIBUTED]->(contrib)
    )
    SET c.fundsRaisedAmount = coalesce(c.fundsRaisedAmount, 0) + CASE
        WHEN $paymentStatus = 'succeeded' THEN $amount ELSE 0 END,
        c.updatedAt = datetime()
    RETURN
      contrib.contributionId AS contributionId,
      contrib.campaignId AS campaignId,
      contrib.amount AS amount,
      contrib.currency AS currency,
      coalesce(contrib.operationalShareAmount, 0) AS operationalShareAmount,
      coalesce(contrib.executionShareAmount, 0) AS executionShareAmount,
      coalesce(contrib.contributorName, '') AS contributorName,
      coalesce(contrib.contributorEmail, '') AS contributorEmail,
      coalesce(contrib.paymentStatus, 'succeeded') AS paymentStatus,
      coalesce(contrib.isAnonymous, false) AS isAnonymous,
      coalesce(contrib.donorVisibility, 'public') AS donorVisibility,
      coalesce(contrib.termsAccepted, true) AS termsAccepted,
      coalesce(contrib.privacyAccepted, true) AS privacyAccepted,
      coalesce(contrib.note, '') AS note,
      toString(contrib.createdAt) AS createdAt
    """
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "campaignId": campaign_id,
                "contributionId": contribution_id,
                "amount": amount,
                "currency": _clean_text(payload.currency) or "GEL",
                "contributorName": _clean_text(payload.contributorName),
                "contributorEmail": _clean_text(payload.contributorEmail),
                "paymentStatus": payment_status,
                "isAnonymous": bool(payload.isAnonymous),
                "donorVisibility": _clean_text(payload.donorVisibility) or "public",
                "termsAccepted": bool(payload.termsAccepted),
                "privacyAccepted": bool(payload.privacyAccepted),
                "note": _clean_text(payload.note),
            },
        )
    if not records:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return records[0].data()


@router.get(
    "/campaigns/{campaign_id}/contributions",
    response_model=List[CampaignContributionOut],
)
def list_campaign_contributions(
    campaign_id: str, limit: int = Query(100, ge=5, le=500)
):
    campaign_id = _clean_text(campaign_id)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    df = _query_df(
        """
        MATCH (c:Campaign {campaignId: $campaignId})-[:HAS_CONTRIBUTION]->(contrib:CampaignContribution)
        RETURN
          contrib.contributionId AS contributionId,
          contrib.campaignId AS campaignId,
          contrib.amount AS amount,
          contrib.currency AS currency,
          coalesce(contrib.operationalShareAmount, 0) AS operationalShareAmount,
          coalesce(contrib.executionShareAmount, 0) AS executionShareAmount,
          coalesce(contrib.contributorName, '') AS contributorName,
          coalesce(contrib.contributorEmail, '') AS contributorEmail,
          coalesce(contrib.paymentStatus, 'succeeded') AS paymentStatus,
          coalesce(contrib.isAnonymous, false) AS isAnonymous,
          coalesce(contrib.donorVisibility, 'public') AS donorVisibility,
          coalesce(contrib.termsAccepted, true) AS termsAccepted,
          coalesce(contrib.privacyAccepted, true) AS privacyAccepted,
          coalesce(contrib.note, '') AS note,
          toString(contrib.createdAt) AS createdAt
        ORDER BY contrib.createdAt DESC
        LIMIT $limit
        """,
        {"campaignId": campaign_id, "limit": int(limit)},
    )
    return df.to_dict(orient="records") if not df.empty else []


@router.post(
    "/campaigns/{campaign_id}/contributions/checkout",
    response_model=CampaignCheckoutOut,
)
def create_contribution_checkout(
    campaign_id: str, payload: CampaignCheckoutRequest
):
    if not ENABLE_PAYMENTS:
        raise HTTPException(status_code=400, detail="Payments are disabled.")
    campaign_id = _clean_text(campaign_id)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    amount = _safe_float(payload.amount, 0.0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Contribution amount must be positive")
    if MAX_CONTRIBUTION_AMOUNT > 0 and amount > MAX_CONTRIBUTION_AMOUNT:
        raise HTTPException(status_code=400, detail="Contribution amount exceeds limit")
    if not payload.termsAccepted or not payload.privacyAccepted:
        raise HTTPException(status_code=400, detail="Terms and privacy consent are required")
    contribution_id = str(uuid4())
    checkout_id = str(uuid4())
    payment_status = "initiated"
    query = """
    MATCH (c:Campaign {campaignId: $campaignId})
    WITH c, $amount AS amount, coalesce(c.operationalFeePercent, 0) AS feePercent
    WITH c,
      amount,
      feePercent,
      round(amount * (feePercent / 100.0), 2) AS operationalShareAmount,
      amount - round(amount * (feePercent / 100.0), 2) AS executionShareAmount
    CREATE (contrib:CampaignContribution {
      contributionId: $contributionId,
      campaignId: $campaignId,
      amount: amount,
      currency: $currency,
      operationalShareAmount: operationalShareAmount,
      executionShareAmount: executionShareAmount,
      contributorName: $contributorName,
      contributorEmail: $contributorEmail,
      paymentStatus: $paymentStatus,
      isAnonymous: $isAnonymous,
      donorVisibility: $donorVisibility,
      termsAccepted: $termsAccepted,
      privacyAccepted: $privacyAccepted,
      note: $note,
      paymentMethod: $paymentMethod,
      checkoutId: $checkoutId,
      createdAt: datetime()
    })
    CREATE (c)-[:HAS_CONTRIBUTION]->(contrib)
    RETURN
      contrib.contributionId AS contributionId,
      contrib.campaignId AS campaignId,
      contrib.amount AS amount,
      contrib.currency AS currency,
      coalesce(contrib.paymentStatus, 'initiated') AS paymentStatus,
      coalesce(contrib.checkoutId, '') AS checkoutId
    """
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "campaignId": campaign_id,
                "contributionId": contribution_id,
                "amount": amount,
                "currency": _clean_text(payload.currency) or "GEL",
                "contributorName": _clean_text(payload.contributorName),
                "contributorEmail": _clean_text(payload.contributorEmail),
                "paymentStatus": payment_status,
                "isAnonymous": bool(payload.isAnonymous),
                "donorVisibility": _clean_text(payload.donorVisibility) or "public",
                "termsAccepted": bool(payload.termsAccepted),
                "privacyAccepted": bool(payload.privacyAccepted),
                "note": _clean_text(payload.note),
                "paymentMethod": _clean_text(payload.paymentMethod) or "card",
                "checkoutId": checkout_id,
            },
        )
    if not records:
        raise HTTPException(status_code=404, detail="Campaign not found")
    row = records[0].data()
    return {
        "checkoutId": row.get("checkoutId"),
        "contributionId": row.get("contributionId"),
        "campaignId": row.get("campaignId"),
        "amount": row.get("amount"),
        "currency": row.get("currency"),
        "paymentStatus": row.get("paymentStatus"),
        "paymentUrl": "",
    }


@router.post("/payments/webhook")
def handle_payment_webhook(payload: PaymentWebhookEvent):
    campaign_id = _clean_text(payload.campaignId)
    contribution_id = _clean_text(payload.contributionId)
    payment_status = _clean_text(payload.paymentStatus).lower()
    if payment_status not in PAYMENT_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid payment status")
    if not campaign_id or not contribution_id:
        raise HTTPException(status_code=400, detail="Campaign and contribution IDs are required")
    query = """
    MATCH (c:Campaign {campaignId: $campaignId})-[:HAS_CONTRIBUTION]->(contrib:CampaignContribution {contributionId: $contributionId})
    SET contrib.paymentStatus = $paymentStatus,
        contrib.processorRef = $processorRef,
        contrib.webhookEventId = $eventId,
        contrib.updatedAt = datetime()
    WITH c
    OPTIONAL MATCH (c)-[:HAS_CONTRIBUTION]->(allContrib:CampaignContribution)
    WITH c, sum(CASE WHEN coalesce(allContrib.paymentStatus, '') = 'succeeded' THEN coalesce(allContrib.amount, 0) ELSE 0 END) AS total
    SET c.fundsRaisedAmount = total,
        c.updatedAt = datetime()
    RETURN
      c.campaignId AS campaignId,
      c.fundsRaisedAmount AS fundsRaisedAmount
    """
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "campaignId": campaign_id,
                "contributionId": contribution_id,
                "paymentStatus": payment_status,
                "processorRef": _clean_text(payload.processorRef),
                "eventId": _clean_text(payload.eventId),
            },
        )
    if not records:
        raise HTTPException(status_code=404, detail="Contribution not found")
    return {"ok": True, "campaignId": campaign_id, "paymentStatus": payment_status}


@router.get(
    "/campaigns/{campaign_id}/funding-summary",
    response_model=CampaignFundingSummaryOut,
)
def get_campaign_funding_summary(campaign_id: str):
    campaign_id = _clean_text(campaign_id)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    df = _query_df(
        """
        MATCH (c:Campaign {campaignId: $campaignId})
        OPTIONAL MATCH (c)-[:HAS_CONTRIBUTION]->(contrib:CampaignContribution)
        WITH c, collect(contrib) AS contributions
        WITH c,
             contributions,
             [x IN contributions WHERE coalesce(x.paymentStatus, '') = 'succeeded'] AS settled
        RETURN
          c.campaignId AS campaignId,
          coalesce(c.fundingTargetAmount, 0) AS fundingTargetAmount,
          reduce(total = 0.0, item IN settled | total + coalesce(item.amount, 0)) AS fundsRaisedAmount,
          coalesce(c.currency, 'GEL') AS currency,
          coalesce(c.operationalFeePercent, 0) AS operationalFeePercent,
          coalesce(c.operationalFeeAmount, 0) AS operationalFeeAmount,
          coalesce(c.executionBudgetAmount, 0) AS executionBudgetAmount,
          size(settled) AS contributorCount,
          reduce(total = 0.0, item IN settled | total + coalesce(item.operationalShareAmount, 0)) AS allocatedOperations,
          reduce(total = 0.0, item IN settled | total + coalesce(item.executionShareAmount, 0)) AS allocatedExecution
        """,
        {"campaignId": campaign_id},
    )
    if df.empty:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return df.iloc[0].to_dict()


# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------

@router.post(
    "/campaigns/{campaign_id}/milestones",
    response_model=CampaignMilestoneOut,
)
def create_campaign_milestone(campaign_id: str, payload: CampaignMilestoneCreate):
    campaign_id = _clean_text(campaign_id)
    title = _clean_text(payload.title)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    if not title:
        raise HTTPException(status_code=400, detail="Milestone title is required")
    milestone_id = str(uuid4())
    query = """
    MATCH (c:Campaign {campaignId: $campaignId})
    CREATE (m:CampaignMilestone {
      milestoneId: $milestoneId,
      campaignId: $campaignId,
      title: $title,
      amountTarget: $amountTarget,
      dueDate: $dueDate,
      status: $status,
      completionPercent: $completionPercent,
      createdAt: datetime(),
      updatedAt: datetime()
    })
    CREATE (c)-[:HAS_MILESTONE]->(m)
    RETURN
      m.milestoneId AS milestoneId,
      m.campaignId AS campaignId,
      m.title AS title,
      coalesce(m.amountTarget, 0) AS amountTarget,
      coalesce(m.dueDate, '') AS dueDate,
      coalesce(m.status, 'Planned') AS status,
      coalesce(m.completionPercent, 0) AS completionPercent,
      toString(m.createdAt) AS createdAt,
      toString(m.updatedAt) AS updatedAt
    """
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "campaignId": campaign_id,
                "milestoneId": milestone_id,
                "title": title,
                "amountTarget": _safe_float(payload.amountTarget, 0.0),
                "dueDate": _clean_text(payload.dueDate),
                "status": _clean_text(payload.status) or "Planned",
                "completionPercent": _safe_float(payload.completionPercent, 0.0),
            },
        )
    if not records:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return records[0].data()


@router.get(
    "/campaigns/{campaign_id}/milestones",
    response_model=List[CampaignMilestoneOut],
)
def list_campaign_milestones(
    campaign_id: str, limit: int = Query(100, ge=5, le=500)
):
    campaign_id = _clean_text(campaign_id)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    df = _query_df(
        """
        MATCH (c:Campaign {campaignId: $campaignId})-[:HAS_MILESTONE]->(m:CampaignMilestone)
        RETURN
          m.milestoneId AS milestoneId,
          m.campaignId AS campaignId,
          m.title AS title,
          coalesce(m.amountTarget, 0) AS amountTarget,
          coalesce(m.dueDate, '') AS dueDate,
          coalesce(m.status, 'Planned') AS status,
          coalesce(m.completionPercent, 0) AS completionPercent,
          toString(m.createdAt) AS createdAt,
          toString(m.updatedAt) AS updatedAt
        ORDER BY m.dueDate ASC, m.createdAt DESC
        LIMIT $limit
        """,
        {"campaignId": campaign_id, "limit": int(limit)},
    )
    return df.to_dict(orient="records") if not df.empty else []


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------

@router.post(
    "/campaigns/{campaign_id}/expenses",
    response_model=CampaignExpenseOut,
)
def create_campaign_expense(campaign_id: str, payload: CampaignExpenseCreate):
    campaign_id = _clean_text(campaign_id)
    category = _clean_text(payload.category)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    if not category:
        raise HTTPException(status_code=400, detail="Expense category is required")
    amount = _safe_float(payload.amount, 0.0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Expense amount must be positive")
    expense_id = str(uuid4())
    query = """
    MATCH (c:Campaign {campaignId: $campaignId})
    CREATE (e:CampaignExpense {
      expenseId: $expenseId,
      campaignId: $campaignId,
      category: $category,
      vendor: $vendor,
      amount: $amount,
      currency: $currency,
      receiptLink: $receiptLink,
      approvedBy: $approvedBy,
      approvalStatus: $approvalStatus,
      milestoneId: $milestoneId,
      createdAt: datetime()
    })
    CREATE (c)-[:HAS_EXPENSE]->(e)
    WITH e
    OPTIONAL MATCH (m:CampaignMilestone {milestoneId: $milestoneId})
    FOREACH (_ IN CASE WHEN m IS NULL THEN [] ELSE [1] END |
      MERGE (m)-[:HAS_EXPENSE]->(e)
    )
    RETURN
      e.expenseId AS expenseId,
      e.campaignId AS campaignId,
      e.category AS category,
      coalesce(e.vendor, '') AS vendor,
      e.amount AS amount,
      coalesce(e.currency, 'GEL') AS currency,
      coalesce(e.receiptLink, '') AS receiptLink,
      coalesce(e.approvedBy, '') AS approvedBy,
      coalesce(e.approvalStatus, 'Pending') AS approvalStatus,
      coalesce(e.milestoneId, '') AS milestoneId,
      toString(e.createdAt) AS createdAt
    """
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "campaignId": campaign_id,
                "expenseId": expense_id,
                "category": category,
                "vendor": _clean_text(payload.vendor),
                "amount": amount,
                "currency": _clean_text(payload.currency) or "GEL",
                "receiptLink": _clean_text(payload.receiptLink),
                "approvedBy": _clean_text(payload.approvedBy),
                "approvalStatus": _clean_text(payload.approvalStatus) or "Pending",
                "milestoneId": _clean_text(payload.milestoneId),
            },
        )
    if not records:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return records[0].data()


@router.get(
    "/campaigns/{campaign_id}/expenses",
    response_model=List[CampaignExpenseOut],
)
def list_campaign_expenses(
    campaign_id: str, limit: int = Query(200, ge=5, le=1000)
):
    campaign_id = _clean_text(campaign_id)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    df = _query_df(
        """
        MATCH (c:Campaign {campaignId: $campaignId})-[:HAS_EXPENSE]->(e:CampaignExpense)
        RETURN
          e.expenseId AS expenseId,
          e.campaignId AS campaignId,
          e.category AS category,
          coalesce(e.vendor, '') AS vendor,
          e.amount AS amount,
          coalesce(e.currency, 'GEL') AS currency,
          coalesce(e.receiptLink, '') AS receiptLink,
          coalesce(e.approvedBy, '') AS approvedBy,
          coalesce(e.approvalStatus, 'Pending') AS approvalStatus,
          coalesce(e.milestoneId, '') AS milestoneId,
          toString(e.createdAt) AS createdAt
        ORDER BY e.createdAt DESC
        LIMIT $limit
        """,
        {"campaignId": campaign_id, "limit": int(limit)},
    )
    return df.to_dict(orient="records") if not df.empty else []


# ---------------------------------------------------------------------------
# Proof
# ---------------------------------------------------------------------------

@router.post(
    "/campaigns/{campaign_id}/proof",
    response_model=CampaignProofOut,
)
def create_campaign_proof(campaign_id: str, payload: CampaignProofCreate):
    campaign_id = _clean_text(campaign_id)
    artifact_type = _clean_text(payload.artifactType)
    url = _clean_text(payload.url)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    if not artifact_type or not url:
        raise HTTPException(
            status_code=400, detail="Proof type and URL are required"
        )
    proof_id = str(uuid4())
    query = """
    MATCH (c:Campaign {campaignId: $campaignId})
    CREATE (p:CampaignProof {
      proofId: $proofId,
      campaignId: $campaignId,
      artifactType: $artifactType,
      caption: $caption,
      url: $url,
      uploadedBy: $uploadedBy,
      verificationStatus: $verificationStatus,
      milestoneId: $milestoneId,
      createdAt: datetime()
    })
    CREATE (c)-[:HAS_PROOF]->(p)
    WITH p
    OPTIONAL MATCH (m:CampaignMilestone {milestoneId: $milestoneId})
    FOREACH (_ IN CASE WHEN m IS NULL THEN [] ELSE [1] END |
      MERGE (m)-[:HAS_PROOF]->(p)
    )
    RETURN
      p.proofId AS proofId,
      p.campaignId AS campaignId,
      p.artifactType AS artifactType,
      coalesce(p.caption, '') AS caption,
      p.url AS url,
      coalesce(p.uploadedBy, '') AS uploadedBy,
      coalesce(p.verificationStatus, 'Pending') AS verificationStatus,
      coalesce(p.milestoneId, '') AS milestoneId,
      toString(p.createdAt) AS createdAt
    """
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "campaignId": campaign_id,
                "proofId": proof_id,
                "artifactType": artifact_type,
                "caption": _clean_text(payload.caption),
                "url": url,
                "uploadedBy": _clean_text(payload.uploadedBy),
                "verificationStatus": _clean_text(payload.verificationStatus) or "Pending",
                "milestoneId": _clean_text(payload.milestoneId),
            },
        )
    if not records:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return records[0].data()


@router.get(
    "/campaigns/{campaign_id}/proof",
    response_model=List[CampaignProofOut],
)
def list_campaign_proof(
    campaign_id: str, limit: int = Query(200, ge=5, le=1000)
):
    campaign_id = _clean_text(campaign_id)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    df = _query_df(
        """
        MATCH (c:Campaign {campaignId: $campaignId})-[:HAS_PROOF]->(p:CampaignProof)
        RETURN
          p.proofId AS proofId,
          p.campaignId AS campaignId,
          p.artifactType AS artifactType,
          coalesce(p.caption, '') AS caption,
          p.url AS url,
          coalesce(p.uploadedBy, '') AS uploadedBy,
          coalesce(p.verificationStatus, 'Pending') AS verificationStatus,
          coalesce(p.milestoneId, '') AS milestoneId,
          toString(p.createdAt) AS createdAt
        ORDER BY p.createdAt DESC
        LIMIT $limit
        """,
        {"campaignId": campaign_id, "limit": int(limit)},
    )
    return df.to_dict(orient="records") if not df.empty else []


# ---------------------------------------------------------------------------
# Partners
# ---------------------------------------------------------------------------

@router.post(
    "/campaigns/{campaign_id}/partners",
    response_model=CampaignPartnerOut,
)
def create_campaign_partner(campaign_id: str, payload: CampaignPartnerCreate):
    campaign_id = _clean_text(campaign_id)
    name = _clean_text(payload.name)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    if not name:
        raise HTTPException(status_code=400, detail="Partner name is required")
    partner_id = str(uuid4())
    query = """
    MATCH (c:Campaign {campaignId: $campaignId})
    CREATE (p:CommunityPartner {
      partnerId: $partnerId,
      campaignId: $campaignId,
      name: $name,
      role: $role,
      contact: $contact,
      verificationNotes: $verificationNotes,
      createdAt: datetime()
    })
    CREATE (c)-[:PARTNERED_WITH]->(p)
    RETURN
      p.partnerId AS partnerId,
      p.campaignId AS campaignId,
      p.name AS name,
      coalesce(p.role, '') AS role,
      coalesce(p.contact, '') AS contact,
      coalesce(p.verificationNotes, '') AS verificationNotes,
      toString(p.createdAt) AS createdAt
    """
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "campaignId": campaign_id,
                "partnerId": partner_id,
                "name": name,
                "role": _clean_text(payload.role),
                "contact": _clean_text(payload.contact),
                "verificationNotes": _clean_text(payload.verificationNotes),
            },
        )
    if not records:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return records[0].data()


@router.get(
    "/campaigns/{campaign_id}/partners",
    response_model=List[CampaignPartnerOut],
)
def list_campaign_partners(
    campaign_id: str, limit: int = Query(100, ge=5, le=500)
):
    campaign_id = _clean_text(campaign_id)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    df = _query_df(
        """
        MATCH (c:Campaign {campaignId: $campaignId})-[:PARTNERED_WITH]->(p:CommunityPartner)
        RETURN
          p.partnerId AS partnerId,
          p.campaignId AS campaignId,
          p.name AS name,
          coalesce(p.role, '') AS role,
          coalesce(p.contact, '') AS contact,
          coalesce(p.verificationNotes, '') AS verificationNotes,
          toString(p.createdAt) AS createdAt
        ORDER BY p.createdAt DESC
        LIMIT $limit
        """,
        {"campaignId": campaign_id, "limit": int(limit)},
    )
    return df.to_dict(orient="records") if not df.empty else []


# ---------------------------------------------------------------------------
# Campaign updates
# ---------------------------------------------------------------------------

@router.post(
    "/campaigns/{campaign_id}/updates",
    response_model=CampaignUpdateOut,
)
def create_campaign_update(campaign_id: str, payload: CampaignUpdateCreate):
    campaign_id = _clean_text(campaign_id)
    message = _clean_text(payload.message)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    if not message:
        raise HTTPException(status_code=400, detail="Update message is required")
    update_id = str(uuid4())
    query = """
    MATCH (c:Campaign {campaignId: $campaignId})
    CREATE (u:CampaignUpdate {
      updateId: $updateId,
      campaignId: $campaignId,
      message: $message,
      createdBy: $createdBy,
      status: $status,
      createdAt: datetime()
    })
    CREATE (c)-[:HAS_UPDATE]->(u)
    RETURN
      u.updateId AS updateId,
      u.campaignId AS campaignId,
      u.message AS message,
      coalesce(u.createdBy, '') AS createdBy,
      coalesce(u.status, '') AS status,
      toString(u.createdAt) AS createdAt
    """
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "campaignId": campaign_id,
                "updateId": update_id,
                "message": message,
                "createdBy": _clean_text(payload.createdBy),
                "status": _clean_text(payload.status),
            },
        )
    if not records:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return records[0].data()


@router.get(
    "/campaigns/{campaign_id}/updates",
    response_model=List[CampaignUpdateOut],
)
def list_campaign_updates(
    campaign_id: str, limit: int = Query(200, ge=5, le=1000)
):
    campaign_id = _clean_text(campaign_id)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    df = _query_df(
        """
        MATCH (c:Campaign {campaignId: $campaignId})-[:HAS_UPDATE]->(u:CampaignUpdate)
        RETURN
          u.updateId AS updateId,
          u.campaignId AS campaignId,
          u.message AS message,
          coalesce(u.createdBy, '') AS createdBy,
          coalesce(u.status, '') AS status,
          toString(u.createdAt) AS createdAt
        ORDER BY u.createdAt DESC
        LIMIT $limit
        """,
        {"campaignId": campaign_id, "limit": int(limit)},
    )
    return df.to_dict(orient="records") if not df.empty else []



# ---------------------------------------------------------------------------
# Campaign communication messages
# ---------------------------------------------------------------------------

def _campaign_message_return(alias: str = "m") -> str:
    return f"""
      {alias}.messageId AS messageId,
      {alias}.campaignId AS campaignId,
      coalesce({alias}.channel, 'whatsapp') AS channel,
      coalesce({alias}.language, 'ka') AS language,
      coalesce({alias}.tone, 'clear') AS tone,
      coalesce({alias}.title, '') AS title,
      coalesce({alias}.body, '') AS body,
      coalesce({alias}.callToAction, '') AS callToAction,
      coalesce({alias}.status, 'Draft') AS status,
      coalesce({alias}.segmentId, '') AS segmentId,
      coalesce({alias}.generatedByAi, false) AS generatedByAi,
      coalesce({alias}.promptContext, '') AS promptContext,
      toString({alias}.createdAt) AS createdAt,
      toString({alias}.updatedAt) AS updatedAt
    """


def _normalise_campaign_message_payload(payload: CampaignMessageCreate) -> dict:
    channel = (_clean_text(payload.channel) or "whatsapp").lower()
    if channel not in {"email", "whatsapp", "slack", "sms", "social", "field"}:
        channel = "whatsapp"
    language = (_clean_text(payload.language) or "ka").lower()
    if language not in {"ka", "en", "bilingual"}:
        language = "ka"
    status = _clean_text(payload.status) or "Draft"
    if status not in {"Draft", "Ready", "Sent", "Archived"}:
        status = "Draft"
    return {
        "channel": channel,
        "language": language,
        "tone": _clean_text(payload.tone) or "clear",
        "title": _clean_text(payload.title),
        "body": _clean_text(payload.body),
        "callToAction": _clean_text(payload.callToAction),
        "status": status,
        "segmentId": _clean_text(payload.segmentId),
        "generatedByAi": bool(payload.generatedByAi),
        "promptContext": _clean_text(payload.promptContext),
    }


@router.post(
    "/campaigns/{campaign_id}/messages/generate",
    response_model=CampaignMessageSuggestionsOut,
)
def generate_campaign_messages(campaign_id: str, payload: CampaignMessageGenerateRequest):
    campaign = get_campaign(campaign_id)
    channel = (_clean_text(payload.channel) or "whatsapp").lower()
    language = (_clean_text(payload.language) or "ka").lower()
    tone = _clean_text(payload.tone) or "clear"
    instructions = _clean_text(payload.instructions)
    name = _clean_text(campaign.get("name")) or "campaign"
    topic = _clean_text(campaign.get("topic")) or name
    objective = _clean_text(campaign.get("objective")) or _clean_text(campaign.get("problemDescription"))
    target = _clean_text(campaign.get("targetGroup")) or "supporters"
    city = _clean_text(campaign.get("locationCity"))
    location = f" in {city}" if city else ""
    cta_en = "Open the link, read the proposal, and share your view."
    cta_ka = "გახსენით ბმული, გაეცანით ინიციატივას და გაგვიზიარეთ თქვენი აზრი."
    default_objective_en = "to understand priorities and coordinate action"
    default_objective_ka = "პრიორიტეტების გაგება და ერთობლივი მოქმედება"
    if language == "en":
        title = f"Join the conversation: {topic}"
        body = (
            f"We are preparing {name}{location} and want input from {target}. "
            f"The goal is: {objective or default_objective_en}. "
            f"{instructions + ' ' if instructions else ''}{cta_en}"
        )
        cta = cta_en
    elif language == "bilingual":
        title = f"{topic} / მონაწილეობა"
        body = (
            f"We are preparing {name}{location} and want input from {target}. "
            f"Goal: {objective or default_objective_en}. {cta_en}\n\n"
            f"ვამზადებთ კამპანიას: {name}. გვჭირდება საზოგადოების უკუკავშირი. "
            f"მიზანია: {objective or default_objective_ka}. {cta_ka}"
        )
        cta = f"{cta_en} / {cta_ka}"
    else:
        title = f"ჩაერთეთ: {topic}"
        body = (
            f"ვამზადებთ კამპანიას: {name}. გვჭირდება {target}-ის უკუკავშირი. "
            f"მიზანია: {objective or default_objective_ka}. "
            f"{instructions + ' ' if instructions else ''}{cta_ka}"
        )
        cta = cta_ka
    if channel == "email" and language != "ka":
        title = f"Invitation: {topic}"
    elif channel == "slack":
        title = f"Campaign update: {topic}"
    message = CampaignMessageCreate(
        channel=channel,
        language=language,
        tone=tone,
        title=title,
        body=body,
        callToAction=cta,
        status="Draft",
        generatedByAi=False,
        promptContext=instructions,
    )
    return {"messages": [message]}


@router.post(
    "/campaigns/{campaign_id}/messages",
    response_model=CampaignMessageOut,
)
def create_campaign_message(campaign_id: str, payload: CampaignMessageCreate):
    campaign_id = _clean_text(campaign_id)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    values = _normalise_campaign_message_payload(payload)
    if not values["body"]:
        raise HTTPException(status_code=400, detail="Message body is required")
    message_id = str(uuid4())
    query = f"""
    MATCH (c:Campaign {{campaignId: $campaignId}})
    CREATE (m:CampaignMessage {{
      messageId: $messageId,
      campaignId: $campaignId,
      channel: $channel,
      language: $language,
      tone: $tone,
      title: $title,
      body: $body,
      callToAction: $callToAction,
      status: $status,
      segmentId: $segmentId,
      generatedByAi: $generatedByAi,
      promptContext: $promptContext,
      createdAt: datetime(),
      updatedAt: datetime()
    }})
    CREATE (c)-[:HAS_MESSAGE]->(m)
    RETURN
      {_campaign_message_return('m')}
    """
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {"campaignId": campaign_id, "messageId": message_id, **values},
        )
    if not records:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return records[0].data()


@router.get(
    "/campaigns/{campaign_id}/messages",
    response_model=List[CampaignMessageOut],
)
def list_campaign_messages(campaign_id: str, limit: int = Query(100, ge=1, le=500)):
    campaign_id = _clean_text(campaign_id)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    df = _query_df(
        f"""
        MATCH (c:Campaign {{campaignId: $campaignId}})-[:HAS_MESSAGE]->(m:CampaignMessage)
        RETURN
          {_campaign_message_return('m')}
        ORDER BY m.createdAt DESC
        LIMIT $limit
        """,
        {"campaignId": campaign_id, "limit": int(limit)},
    )
    return df.to_dict(orient="records") if not df.empty else []


@router.patch(
    "/campaigns/{campaign_id}/messages/{message_id}",
    response_model=CampaignMessageOut,
)
def update_campaign_message(campaign_id: str, message_id: str, payload: CampaignMessageUpdate):
    campaign_id = _clean_text(campaign_id)
    message_id = _clean_text(message_id)
    if not campaign_id or not message_id:
        raise HTTPException(status_code=400, detail="Campaign and message IDs are required")
    existing_df = _query_df(
        f"""
        MATCH (c:Campaign {{campaignId: $campaignId}})-[:HAS_MESSAGE]->(m:CampaignMessage {{messageId: $messageId}})
        RETURN
          {_campaign_message_return('m')}
        LIMIT 1
        """,
        {"campaignId": campaign_id, "messageId": message_id},
    )
    if existing_df.empty:
        raise HTTPException(status_code=404, detail="Campaign message not found")
    existing = existing_df.iloc[0].to_dict()
    merged = CampaignMessageCreate(
        channel=payload.channel if payload.channel is not None else existing.get("channel"),
        language=payload.language if payload.language is not None else existing.get("language"),
        tone=payload.tone if payload.tone is not None else existing.get("tone"),
        title=payload.title if payload.title is not None else existing.get("title"),
        body=payload.body if payload.body is not None else existing.get("body"),
        callToAction=payload.callToAction if payload.callToAction is not None else existing.get("callToAction"),
        status=payload.status if payload.status is not None else existing.get("status"),
        segmentId=payload.segmentId if payload.segmentId is not None else existing.get("segmentId"),
        generatedByAi=payload.generatedByAi if payload.generatedByAi is not None else existing.get("generatedByAi"),
        promptContext=payload.promptContext if payload.promptContext is not None else existing.get("promptContext"),
    )
    values = _normalise_campaign_message_payload(merged)
    if not values["body"]:
        raise HTTPException(status_code=400, detail="Message body is required")
    query = f"""
    MATCH (c:Campaign {{campaignId: $campaignId}})-[:HAS_MESSAGE]->(m:CampaignMessage {{messageId: $messageId}})
    SET m.channel = $channel,
        m.language = $language,
        m.tone = $tone,
        m.title = $title,
        m.body = $body,
        m.callToAction = $callToAction,
        m.status = $status,
        m.segmentId = $segmentId,
        m.generatedByAi = $generatedByAi,
        m.promptContext = $promptContext,
        m.updatedAt = datetime()
    RETURN
      {_campaign_message_return('m')}
    """
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(session, query, {"campaignId": campaign_id, "messageId": message_id, **values})
    if not records:
        raise HTTPException(status_code=404, detail="Campaign message not found")
    return records[0].data()


@router.delete("/campaigns/{campaign_id}/messages/{message_id}")
def delete_campaign_message(campaign_id: str, message_id: str):
    campaign_id = _clean_text(campaign_id)
    message_id = _clean_text(message_id)
    if not campaign_id or not message_id:
        raise HTTPException(status_code=400, detail="Campaign and message IDs are required")
    query = """
    MATCH (c:Campaign {campaignId: $campaignId})-[r:HAS_MESSAGE]->(m:CampaignMessage {messageId: $messageId})
    DETACH DELETE m
    RETURN count(r) AS deleted
    """
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(session, query, {"campaignId": campaign_id, "messageId": message_id})
    deleted = int(records[0].data().get("deleted", 0)) if records else 0
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Campaign message not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Campaign tasks
# ---------------------------------------------------------------------------

@router.post(
    "/campaigns/{campaign_id}/tasks",
    response_model=CampaignTaskOut,
)
def create_campaign_task(campaign_id: str, payload: CampaignTaskCreate):
    campaign_id = _clean_text(campaign_id)
    title = _clean_text(payload.title)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    if not title:
        raise HTTPException(status_code=400, detail="Task title is required")
    status = payload.status if payload.status in TASK_STATUSES else "Open"
    query = """
    MATCH (c:Campaign {campaignId: $campaignId})
    CREATE (t:Task {
      taskId: randomUUID(),
      campaignId: $campaignId,
      milestoneId: $milestoneId,
      title: $title,
      description: $description,
      status: $status,
      dueDate: $dueDate,
      createdAt: datetime(),
      updatedAt: datetime()
    })
    CREATE (c)-[:HAS_TASK]->(t)
    WITH t
    OPTIONAL MATCH (p:Person {email: $assigneeEmail})
    FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END |
      MERGE (p)-[:HAS_TASK]->(t)
    )
    RETURN
      t.taskId AS taskId,
      t.campaignId AS campaignId,
      coalesce(t.milestoneId, '') AS milestoneId,
      t.title AS title,
      coalesce(t.description, '') AS description,
      coalesce(t.status, 'Open') AS status,
      coalesce(t.dueDate, '') AS dueDate,
      coalesce($assigneeEmail, '') AS assigneeEmail,
      coalesce(p.firstName, '') + CASE WHEN coalesce(p.lastName, '') = '' THEN '' ELSE ' ' + p.lastName END AS assigneeName,
      toString(t.createdAt) AS createdAt,
      toString(t.updatedAt) AS updatedAt
    """
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "campaignId": campaign_id,
                "title": title,
                "description": _clean_text(payload.description),
                "status": status,
                "dueDate": _clean_text(payload.dueDate),
                "assigneeEmail": _clean_text(payload.assigneeEmail),
                "milestoneId": _clean_text(payload.milestoneId),
            },
        )
    if not records:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return records[0].data()


@router.get(
    "/campaigns/{campaign_id}/tasks",
    response_model=List[CampaignTaskOut],
)
def list_campaign_tasks(
    campaign_id: str, limit: int = Query(200, ge=5, le=1000)
):
    campaign_id = _clean_text(campaign_id)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    df = _query_df(
        """
        MATCH (c:Campaign {campaignId: $campaignId})-[:HAS_TASK]->(t:Task)
        OPTIONAL MATCH (p:Person)-[:HAS_TASK]->(t)
        RETURN
          t.taskId AS taskId,
          t.campaignId AS campaignId,
          coalesce(t.milestoneId, '') AS milestoneId,
          t.title AS title,
          coalesce(t.description, '') AS description,
          coalesce(t.status, 'Open') AS status,
          coalesce(t.dueDate, '') AS dueDate,
          coalesce(p.email, '') AS assigneeEmail,
          coalesce(p.firstName, '') + CASE WHEN coalesce(p.lastName, '') = '' THEN '' ELSE ' ' + p.lastName END AS assigneeName,
          toString(t.createdAt) AS createdAt,
          toString(t.updatedAt) AS updatedAt
        ORDER BY t.createdAt DESC
        LIMIT $limit
        """,
        {"campaignId": campaign_id, "limit": int(limit)},
    )
    return df.to_dict(orient="records") if not df.empty else []


# ---------------------------------------------------------------------------
# Transparency / audit
# ---------------------------------------------------------------------------

@router.get(
    "/campaigns/{campaign_id}/transparency",
    response_model=CampaignTransparencyOut,
)
def get_campaign_transparency(campaign_id: str):
    campaign_id = _clean_text(campaign_id)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    df = _query_df(
        """
        MATCH (c:Campaign {campaignId: $campaignId})
        OPTIONAL MATCH (c)-[:HAS_EXPENSE]->(e:CampaignExpense)
        OPTIONAL MATCH (c)-[:HAS_PROOF]->(p:CampaignProof)
        WITH c,
             sum(CASE WHEN coalesce(e.approvalStatus, 'Pending') = 'Approved' THEN coalesce(e.amount, 0) ELSE 0 END) AS amountSpent,
             count(CASE WHEN coalesce(e.approvalStatus, 'Pending') = 'Approved' THEN e ELSE null END) AS expenseCount,
             count(DISTINCT p) AS proofCount
        RETURN
          c.campaignId AS campaignId,
          coalesce(c.fundingTargetAmount, 0) AS fundingTargetAmount,
          coalesce(c.fundsRaisedAmount, 0) AS fundsRaisedAmount,
          amountSpent AS amountSpent,
          coalesce(c.operationalFeeAmount, 0) AS operationalFeeAmount,
          coalesce(c.executionBudgetAmount, 0) AS executionBudgetAmount,
          CASE
            WHEN coalesce(c.fundsRaisedAmount, 0) - amountSpent - coalesce(c.operationalFeeAmount, 0) < 0
            THEN 0
            ELSE coalesce(c.fundsRaisedAmount, 0) - amountSpent - coalesce(c.operationalFeeAmount, 0)
          END AS remainingBalance,
          expenseCount AS expenseCount,
          proofCount AS proofCount
        """,
        {"campaignId": campaign_id},
    )
    if df.empty:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return df.iloc[0].to_dict()


@router.get(
    "/campaigns/{campaign_id}/audit",
    response_model=List[CampaignAuditEventOut],
)
def list_campaign_audit_events(
    campaign_id: str, limit: int = Query(200, ge=5, le=1000)
):
    campaign_id = _clean_text(campaign_id)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    df = _query_df(
        """
        CALL {
          MATCH (c:Campaign {campaignId: $campaignId})-[:HAS_CONTRIBUTION]->(contrib:CampaignContribution)
          RETURN
            'contribution' AS eventType,
            'Contribution ' + toString(contrib.amount) + ' ' + coalesce(contrib.currency, 'GEL') AS summary,
            contrib.createdAt AS createdAt
          UNION ALL
          MATCH (c:Campaign {campaignId: $campaignId})-[:HAS_EXPENSE]->(exp:CampaignExpense)
          RETURN
            'expense' AS eventType,
            'Expense ' + coalesce(exp.category, 'Item') + ' - ' + toString(exp.amount) + ' ' + coalesce(exp.currency, 'GEL') AS summary,
            exp.createdAt AS createdAt
          UNION ALL
          MATCH (c:Campaign {campaignId: $campaignId})-[:HAS_PROOF]->(p:CampaignProof)
          RETURN
            'proof' AS eventType,
            'Proof ' + coalesce(p.artifactType, 'artifact') AS summary,
            p.createdAt AS createdAt
          UNION ALL
          MATCH (c:Campaign {campaignId: $campaignId})-[:HAS_UPDATE]->(u:CampaignUpdate)
          RETURN
            'update' AS eventType,
            coalesce(u.message, '') AS summary,
            u.createdAt AS createdAt
        }
        RETURN
          eventType,
          summary,
          toString(createdAt) AS createdAt
        ORDER BY createdAt DESC
        LIMIT $limit
        """,
        {"campaignId": campaign_id, "limit": int(limit)},
    )
    return df.to_dict(orient="records") if not df.empty else []


# ---------------------------------------------------------------------------
# Volunteers
# ---------------------------------------------------------------------------

@router.post(
    "/campaigns/{campaign_id}/volunteers",
    response_model=CampaignVolunteerOut,
)
def create_campaign_volunteer(campaign_id: str, payload: CampaignVolunteerCreate):
    campaign_id = _clean_text(campaign_id)
    name = _clean_text(payload.name)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    if not name:
        raise HTTPException(status_code=400, detail="Volunteer name is required")
    volunteer_id = str(uuid4())
    query = """
    MATCH (c:Campaign {campaignId: $campaignId})
    CREATE (v:CampaignVolunteer {
      volunteerId: $volunteerId,
      campaignId: $campaignId,
      name: $name,
      email: $email,
      phone: $phone,
      role: $role,
      notes: $notes,
      createdAt: datetime()
    })
    CREATE (c)-[:HAS_VOLUNTEER]->(v)
    WITH v
    OPTIONAL MATCH (p:Person {email: $email})
    FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END |
      MERGE (p)-[:VOLUNTEERED_FOR]->(v)
    )
    RETURN
      v.volunteerId AS volunteerId,
      v.campaignId AS campaignId,
      v.name AS name,
      coalesce(v.email, '') AS email,
      coalesce(v.phone, '') AS phone,
      coalesce(v.role, '') AS role,
      coalesce(v.notes, '') AS notes,
      toString(v.createdAt) AS createdAt
    """
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "campaignId": campaign_id,
                "volunteerId": volunteer_id,
                "name": name,
                "email": _clean_text(payload.email),
                "phone": _clean_text(payload.phone),
                "role": _clean_text(payload.role),
                "notes": _clean_text(payload.notes),
            },
        )
    if not records:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return records[0].data()


@router.get(
    "/campaigns/{campaign_id}/volunteers",
    response_model=List[CampaignVolunteerOut],
)
def list_campaign_volunteers(
    campaign_id: str, limit: int = Query(200, ge=5, le=1000)
):
    campaign_id = _clean_text(campaign_id)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    df = _query_df(
        """
        MATCH (c:Campaign {campaignId: $campaignId})-[:HAS_VOLUNTEER]->(v:CampaignVolunteer)
        RETURN
          v.volunteerId AS volunteerId,
          v.campaignId AS campaignId,
          v.name AS name,
          coalesce(v.email, '') AS email,
          coalesce(v.phone, '') AS phone,
          coalesce(v.role, '') AS role,
          coalesce(v.notes, '') AS notes,
          toString(v.createdAt) AS createdAt
        ORDER BY v.createdAt DESC
        LIMIT $limit
        """,
        {"campaignId": campaign_id, "limit": int(limit)},
    )
    return df.to_dict(orient="records") if not df.empty else []


# ---------------------------------------------------------------------------
# Analysis / deliberation
# ---------------------------------------------------------------------------

@router.post("/campaigns/{campaign_id}/analysis", response_model=CampaignOut)
def analyze_campaign(campaign_id: str, payload: CampaignAnalysisRequest):
    campaign_id = _clean_text(campaign_id)
    if not campaign_id:
        raise HTTPException(status_code=400, detail="Campaign ID is required")
    analysis = _generate_campaign_analysis(
        payload.topic,
        payload.legislationText,
        payload.manifestoText,
        payload.expertPrompt,
    )
    driver = get_driver()
    query = f"""
    MATCH (c:Campaign {{campaignId: $campaignId}})
    SET c.topic = $topic,
        c.legislationText = $legislationText,
        c.manifestoText = $manifestoText,
        c.expertPrompt = $expertPrompt,
        c.consensusStatements = $consensusStatements,
        c.polarizationStatements = $polarizationStatements,
        c.updatedAt = datetime()
    RETURN
      {_CAMPAIGN_RETURN}
    """
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "campaignId": campaign_id,
                "topic": _clean_text(payload.topic),
                "legislationText": _clean_text(payload.legislationText),
                "manifestoText": _clean_text(payload.manifestoText),
                "expertPrompt": _clean_text(payload.expertPrompt),
                "consensusStatements": analysis["consensusStatements"],
                "polarizationStatements": analysis["polarizationStatements"],
            },
        )
    if not records:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return records[0].data()


@router.post("/campaigns/{campaign_id}/deliberation", response_model=CampaignOut)
def launch_campaign_deliberation(campaign_id: str):
    df = _query_df(
        f"""
        MATCH (c:Campaign {{campaignId: $campaignId}})
        RETURN
          c.campaignId AS campaignId,
          c.name AS name,
          coalesce(c.topic, '') AS topic,
          coalesce(c.objective, '') AS objective,
          coalesce(c.legislationText, '') AS legislationText,
          coalesce(c.manifestoText, '') AS manifestoText,
          coalesce(c.expertPrompt, '') AS expertPrompt,
          coalesce(c.consensusStatements, []) AS consensusStatements,
          coalesce(c.polarizationStatements, []) AS polarizationStatements,
          coalesce(c.deliberationConversationId, '') AS deliberationConversationId
        LIMIT 1
        """,
        {"campaignId": _clean_text(campaign_id)},
    )
    if df.empty:
        raise HTTPException(status_code=404, detail="Campaign not found")
    row = df.iloc[0].to_dict()
    existing_id = _clean_text(row.get("deliberationConversationId"))
    if existing_id:
        return get_campaign(row.get("campaignId"))
    topic = row.get("topic") or row.get("name") or "Campaign deliberation"
    description = row.get("objective") or "Campaign deliberation conversation."
    convo = create_conversation(
        ConversationCreate(
            topic=topic,
            description=description,
            is_open=True,
            allow_comment_submission=True,
            allow_viz=True,
            moderation_required=False,
        )
    )
    conversation_id = convo.get("id") if isinstance(convo, dict) else None
    statements = list(row.get("consensusStatements") or []) + list(
        row.get("polarizationStatements") or []
    )
    analysis = None
    if not statements:
        analysis = _generate_campaign_analysis(
            row.get("topic"),
            row.get("legislationText"),
            row.get("manifestoText"),
            row.get("expertPrompt"),
        )
        statements = analysis["consensusStatements"] + analysis["polarizationStatements"]
    topic_label = _clean_text(row.get("topic")) or row.get("name") or "Campaign"
    statements = _prepare_seed_statements(statements, topic_label)
    if conversation_id:
        seed_comments(conversation_id, SeedCommentsRequest(comments=statements))
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            MATCH (c:Campaign {campaignId: $campaignId})
            SET c.deliberationConversationId = $conversationId,
                c.updatedAt = datetime()
            FOREACH (_ IN CASE WHEN $updateStatements THEN [1] ELSE [] END |
              SET c.consensusStatements = $consensusStatements,
                  c.polarizationStatements = $polarizationStatements
            )
            """,
            {
                "campaignId": row.get("campaignId"),
                "conversationId": conversation_id,
                "updateStatements": bool(analysis),
                "consensusStatements": analysis["consensusStatements"] if analysis else [],
                "polarizationStatements": analysis["polarizationStatements"] if analysis else [],
            },
        )
    return get_campaign(row.get("campaignId"))


# ---------------------------------------------------------------------------
# Admin: campaign-level endpoints
# ---------------------------------------------------------------------------

@router.get("/admin/contributions", response_model=List[AdminContributionOut])
def admin_contributions(limit: int = Query(200, ge=10, le=1000)):
    df = _query_df(
        """
        MATCH (c:Campaign)-[:HAS_CONTRIBUTION]->(contrib:CampaignContribution)
        RETURN
          contrib.contributionId AS contributionId,
          contrib.campaignId AS campaignId,
          coalesce(c.name, '') AS campaignName,
          contrib.amount AS amount,
          coalesce(contrib.currency, 'GEL') AS currency,
          coalesce(contrib.paymentStatus, '') AS paymentStatus,
          coalesce(contrib.operationalShareAmount, 0) AS operationalShareAmount,
          coalesce(contrib.executionShareAmount, 0) AS executionShareAmount,
          coalesce(contrib.contributorName, '') AS contributorName,
          coalesce(contrib.contributorEmail, '') AS contributorEmail,
          toString(contrib.createdAt) AS createdAt
        ORDER BY contrib.createdAt DESC
        LIMIT $limit
        """,
        {"limit": int(limit)},
    )
    return df.to_dict(orient="records") if not df.empty else []


@router.get("/admin/proof-queue")
def admin_proof_queue(
    status: Optional[str] = Query("Pending"), limit: int = Query(200, ge=10, le=1000)
):
    df = _query_df(
        """
        MATCH (c:Campaign)-[:HAS_PROOF]->(p:CampaignProof)
        WHERE ($status IS NULL OR coalesce(p.verificationStatus, 'Pending') = $status)
        RETURN
          p.proofId AS proofId,
          c.campaignId AS campaignId,
          coalesce(c.name, '') AS campaignName,
          coalesce(p.artifactType, '') AS artifactType,
          coalesce(p.caption, '') AS caption,
          coalesce(p.url, '') AS url,
          coalesce(p.verificationStatus, 'Pending') AS verificationStatus,
          toString(p.createdAt) AS createdAt
        ORDER BY p.createdAt DESC
        LIMIT $limit
        """,
        {"status": _clean_text(status), "limit": int(limit)},
    )
    return df.to_dict(orient="records") if not df.empty else []


@router.patch("/admin/proof/{proof_id}")
def admin_update_proof(proof_id: str, payload: ProofStatusUpdate):
    proof_id = _clean_text(proof_id)
    status = _clean_text(payload.verificationStatus) or "Pending"
    query = """
    MATCH (p:CampaignProof {proofId: $proofId})
    SET p.verificationStatus = $status,
        p.updatedAt = datetime()
    RETURN p.proofId AS proofId, p.verificationStatus AS verificationStatus
    """
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {"proofId": proof_id, "status": status},
        )
    if not records:
        raise HTTPException(status_code=404, detail="Proof not found")
    return records[0].data()


@router.get("/admin/expense-queue")
def admin_expense_queue(
    status: Optional[str] = Query("Pending"), limit: int = Query(200, ge=10, le=1000)
):
    df = _query_df(
        """
        MATCH (c:Campaign)-[:HAS_EXPENSE]->(e:CampaignExpense)
        WHERE ($status IS NULL OR coalesce(e.approvalStatus, 'Pending') = $status)
        RETURN
          e.expenseId AS expenseId,
          c.campaignId AS campaignId,
          coalesce(c.name, '') AS campaignName,
          coalesce(e.category, '') AS category,
          e.amount AS amount,
          coalesce(e.currency, 'GEL') AS currency,
          coalesce(e.approvalStatus, 'Pending') AS approvalStatus,
          coalesce(e.approvedBy, '') AS approvedBy,
          coalesce(e.receiptLink, '') AS receiptLink,
          toString(e.createdAt) AS createdAt
        ORDER BY e.createdAt DESC
        LIMIT $limit
        """,
        {"status": _clean_text(status), "limit": int(limit)},
    )
    return df.to_dict(orient="records") if not df.empty else []


@router.patch("/admin/expenses/{expense_id}")
def admin_update_expense(expense_id: str, payload: ExpenseApprovalUpdate):
    expense_id = _clean_text(expense_id)
    status = _clean_text(payload.approvalStatus) or "Pending"
    query = """
    MATCH (e:CampaignExpense {expenseId: $expenseId})
    SET e.approvalStatus = $status,
        e.approvedBy = $approvedBy,
        e.updatedAt = datetime()
    RETURN e.expenseId AS expenseId, e.approvalStatus AS approvalStatus
    """
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {"expenseId": expense_id, "status": status, "approvedBy": _clean_text(payload.approvedBy)},
        )
    if not records:
        raise HTTPException(status_code=404, detail="Expense not found")
    return records[0].data()


@router.get("/admin/campaign-metrics")
def admin_campaign_metrics():
    totals_df = _query_df(
        """
        MATCH (c:Campaign)
        RETURN count(c) AS totalCampaigns
        """
    )
    funding_df = _query_df(
        """
        MATCH (c:Campaign)-[:HAS_CONTRIBUTION]->(contrib:CampaignContribution)
        WHERE coalesce(contrib.paymentStatus, '') = 'succeeded'
        RETURN
          sum(contrib.amount) AS totalRaised,
          count(contrib) AS contributionCount,
          avg(contrib.amount) AS averageContribution
        """
    )
    completed_df = _query_df(
        """
        MATCH (c:Campaign)
        WHERE coalesce(c.status, '') = 'Completed'
        RETURN count(c) AS completedCount
        """
    )
    verified_df = _query_df(
        """
        MATCH (c:Campaign)-[:HAS_PROOF]->(p:CampaignProof)
        WHERE coalesce(p.verificationStatus, '') = 'Verified'
        RETURN count(DISTINCT c) AS verifiedCount
        """
    )
    variance_df = _query_df(
        """
        MATCH (c:Campaign)
        OPTIONAL MATCH (c)-[:HAS_EXPENSE]->(e:CampaignExpense)
        WITH c,
          sum(CASE WHEN coalesce(e.approvalStatus, 'Pending') = 'Approved' THEN coalesce(e.amount, 0) ELSE 0 END) AS spent
        WITH c, spent, coalesce(c.executionBudgetAmount, 0) AS budget
        WHERE budget > 0
        RETURN avg((spent - budget) / budget) AS avgBudgetVariance
        """
    )
    city_df = _query_df(
        """
        MATCH (c:Campaign)
        WHERE coalesce(c.locationCity, '') <> ''
        RETURN c.locationCity AS city, count(c) AS count
        ORDER BY count DESC
        LIMIT 5
        """
    )
    totals = totals_df.iloc[0].to_dict() if not totals_df.empty else {}
    funding = funding_df.iloc[0].to_dict() if not funding_df.empty else {}
    completed = completed_df.iloc[0].to_dict() if not completed_df.empty else {}
    verified = verified_df.iloc[0].to_dict() if not verified_df.empty else {}
    variance = variance_df.iloc[0].to_dict() if not variance_df.empty else {}
    return {
        "totalCampaigns": int(totals.get("totalCampaigns") or 0),
        "totalRaised": float(funding.get("totalRaised") or 0),
        "contributionCount": int(funding.get("contributionCount") or 0),
        "averageContribution": float(funding.get("averageContribution") or 0),
        "completedCount": int(completed.get("completedCount") or 0),
        "verifiedCount": int(verified.get("verifiedCount") or 0),
        "avgBudgetVariance": float(variance.get("avgBudgetVariance") or 0),
        "topCities": city_df.to_dict(orient="records") if not city_df.empty else [],
    }


@router.post("/admin/campaigns/backfill")
def admin_backfill_campaigns():
    query = """
    MATCH (c:Campaign)
    SET c.problemTitle = coalesce(c.problemTitle, ''),
        c.problemDescription = coalesce(c.problemDescription, ''),
        c.locationCity = coalesce(c.locationCity, ''),
        c.locationDistrict = coalesce(c.locationDistrict, ''),
        c.beneficiaryType = coalesce(c.beneficiaryType, ''),
        c.fundingTargetAmount = coalesce(c.fundingTargetAmount, 0),
        c.currency = coalesce(c.currency, 'GEL'),
        c.fundsRaisedAmount = coalesce(c.fundsRaisedAmount, 0),
        c.operationalFeePercent = coalesce(c.operationalFeePercent, 0),
        c.operationalFeeAmount = coalesce(c.operationalFeeAmount, 0),
        c.executionBudgetAmount = coalesce(c.executionBudgetAmount, 0),
        c.campaignVisibility = coalesce(c.campaignVisibility, 'Public'),
        c.campaignCategory = coalesce(c.campaignCategory, ''),
        c.riskLevel = coalesce(c.riskLevel, ''),
        c.implementationSteps = coalesce(c.implementationSteps, ''),
        c.responsibleOwner = coalesce(c.responsibleOwner, ''),
        c.communityPartner = coalesce(c.communityPartner, ''),
        c.executionStartDate = coalesce(c.executionStartDate, ''),
        c.expectedCompletionDate = coalesce(c.expectedCompletionDate, ''),
        c.updatedAt = datetime()
    RETURN count(c) AS updatedCount
    """
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(session, query, {})
    updated = int(records[0].data().get("updatedCount") or 0) if records else 0
    return {"updated": updated}


@router.post("/admin/campaigns/seed-demo")
def admin_seed_demo_campaign():
    query = """
    MERGE (c:Campaign {name: 'Stray dogs in City X'})
    ON CREATE SET
      c.campaignId = randomUUID(),
      c.problemTitle = 'Reduce stray dog population',
      c.problemDescription = 'Fund shelters, sterilization, and community outreach.',
      c.locationCity = 'City X',
      c.locationDistrict = 'Central',
      c.beneficiaryType = 'Community',
      c.fundingTargetAmount = 25000,
      c.currency = 'GEL',
      c.fundsRaisedAmount = 0,
      c.operationalFeePercent = 10,
      c.operationalFeeAmount = 2500,
      c.executionBudgetAmount = 22500,
      c.campaignVisibility = 'Public',
      c.campaignCategory = 'Public health',
      c.riskLevel = 'Low',
      c.status = 'Funding',
      c.createdAt = datetime(),
      c.updatedAt = datetime()
    WITH c
    OPTIONAL MATCH (c)-[:HAS_MILESTONE]->(m:CampaignMilestone)
    WITH c, count(m) AS milestoneCount
    FOREACH (_ IN CASE WHEN milestoneCount = 0 THEN [1] ELSE [] END |
      CREATE (m1:CampaignMilestone {
        milestoneId: randomUUID(),
        campaignId: c.campaignId,
        title: 'Shelter capacity build-out',
        amountTarget: 12000,
        dueDate: '',
        status: 'Planned',
        completionPercent: 0,
        createdAt: datetime(),
        updatedAt: datetime()
      })
      CREATE (c)-[:HAS_MILESTONE]->(m1)
    )
    RETURN c.campaignId AS campaignId
    """
    driver = get_driver()
    with _db_session(driver) as session:
        records = _execute_write(session, query, {})
    if not records:
        raise HTTPException(status_code=500, detail="Unable to seed demo campaign")
    return {"seeded": True, "campaignId": records[0].data().get("campaignId")}



