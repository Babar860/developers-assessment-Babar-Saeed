from sqlmodel import SQLModel


class GenerateRemittanceResponse(SQLModel):
    status : str
    generated : int