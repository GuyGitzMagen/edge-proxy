from fastapi import FastAPI
from fastapi import Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from flag_engine.engine import get_environment_feature_state
from flag_engine.engine import get_environment_feature_states
from flag_engine.engine import get_identity_feature_states
from flag_engine.environments.builders import build_environment_model
from flag_engine.identities.models import IdentityModel

from .cache import CacheService
from .models import IdentityWithTraits
from .schemas import APIFeatureStateSchema
from .schemas import APITraitSchema
from .settings import Settings
from .sse import router as sse_router
from fastapi_utils.tasks import repeat_every

app = FastAPI()
settings = Settings()
cache_service = CacheService(settings)

fs_schema = APIFeatureStateSchema()
trait_schema = APITraitSchema()


@app.get("/api/v1/flags/")
def flags(feature: str = None, x_environment_key: str = Header(None)):
    environment_document = cache_service.get_environment(x_environment_key)
    environment = build_environment_model(environment_document)

    if feature:
        feature_state = get_environment_feature_state(environment, feature)
        data = fs_schema.dump(feature_state)
    else:
        feature_states = get_environment_feature_states(environment)
        data = fs_schema.dump(feature_states, many=True)

    return JSONResponse(content=data)


def _get_fs_schema(identity_model: IdentityModel):
    return APIFeatureStateSchema(
        context={"identity_identifier": identity_model.identifier},
    )


@app.post("/api/v1/identities/")
def identity(
    input_data: IdentityWithTraits,
    x_environment_key: str = Header(None),
):
    environment_document = cache_service.get_environment(x_environment_key)
    environment = build_environment_model(environment_document)
    identity = IdentityModel(
        identifier=input_data.identifier, environment_api_key=x_environment_key
    )
    trait_models = trait_schema.load(input_data.dict()["traits"], many=True)
    fs_schema = _get_fs_schema(identity)
    flags = get_identity_feature_states(
        environment, identity, override_traits=trait_models
    )
    data = {
        "traits": trait_schema.dump(trait_models, many=True),
        "flags": fs_schema.dump(flags, many=True),
    }
    return JSONResponse(content=data)


@app.on_event("startup")
@repeat_every(seconds=settings.api_poll_frequency, raise_exceptions=True)
def refresh_cache():
    cache_service.refresh()


origins = [
    "http://localhost.tiangolo.com",
    "https://localhost.tiangolo.com",
    "http://localhost",
    "http://localhost:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(sse_router)
