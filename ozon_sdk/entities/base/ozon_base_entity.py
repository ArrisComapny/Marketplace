from pydantic import BaseModel, model_validator


class BaseEntity(BaseModel):

    @model_validator(mode='before')
    @classmethod
    def _drop_nulls(cls, data):
        # Ozon отдаёт часть полей явным null. Поля моделей не Optional, поэтому
        # убираем null до валидации, чтобы сработали значения по умолчанию.
        if isinstance(data, dict):
            return {key: value for key, value in data.items() if value is not None}
        return data
