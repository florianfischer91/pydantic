from __future__ import annotations as _annotations

import warnings
from typing import TYPE_CHECKING, Any, Callable, cast

from pydantic_core import core_schema
from typing_extensions import Literal, Self

from ..config import ConfigDict, ExtraValues, JsonSchemaExtraCallable
from ..errors import PydanticUserError

DEPRECATION_MESSAGE = 'Support for class-based `config` is deprecated, use ConfigDict instead.'


class ConfigWrapper:
    """
    Internal wrapper for Config which exposes ConfigDict items as attributes.
    """

    __slots__ = ('config_dict',)

    config_dict: ConfigDict

    # all annotations are copied directly from ConfigDict, and should be kept up to date, a test will fail if they
    # stop matching
    title: str | None
    str_to_lower: bool
    str_to_upper: bool
    str_strip_whitespace: bool
    str_min_length: int
    str_max_length: int | None
    extra: ExtraValues | None
    frozen: bool
    populate_by_name: bool
    use_enum_values: bool
    validate_assignment: bool
    arbitrary_types_allowed: bool
    from_attributes: bool
    # whether to use the used alias (or first alias for "field required" errors) instead of field_names
    # to construct error `loc`s, default True
    loc_by_alias: bool
    alias_generator: Callable[[str], str] | None
    ignored_types: tuple[type, ...]
    allow_inf_nan: bool
    json_schema_extra: dict[str, object] | JsonSchemaExtraCallable | None

    # new in V2
    strict: bool
    # whether instances of models and dataclasses (including subclass instances) should re-validate, default 'never'
    revalidate_instances: Literal['always', 'never', 'subclass-instances']
    ser_json_timedelta: Literal['iso8601', 'float']
    ser_json_bytes: Literal['utf8', 'base64']
    # whether to validate default values during validation, default False
    validate_default: bool
    validate_return: bool
    protected_namespaces: tuple[str, ...]
    hide_input_in_errors: bool

    def __init__(self, config: ConfigDict | dict[str, Any] | type[Any] | None, *, check: bool = True):
        if check:
            self.config_dict = prepare_config(config)
        else:
            self.config_dict = cast(ConfigDict, config)

    @classmethod
    def for_model(cls, bases: tuple[type[Any], ...], namespace: dict[str, Any], kwargs: dict[str, Any]) -> Self:
        """
        Build a new `ConfigDict` instance for a `BaseModel` based on (from lowest to highest)
        - options defined in base
        - options defined in namespace
        - options defined via kwargs

        :param bases: tuple of base classes
        :param namespace: namespace of the class being created
        :param kwargs: kwargs passed to the class being created
        """

        config_new = ConfigDict()
        for base in bases:
            config = getattr(base, 'model_config', None)
            if config:
                config_new.update(config.copy())

        config_class_from_namespace = namespace.get('Config')
        config_dict_from_namespace = namespace.get('model_config')

        if config_class_from_namespace and config_dict_from_namespace:
            raise PydanticUserError('"Config" and "model_config" cannot be used together', code='config-both')

        config_from_namespace = config_dict_from_namespace or prepare_config(config_class_from_namespace)

        if config_from_namespace is not None:
            config_new.update(config_from_namespace)

        for k in list(kwargs.keys()):
            if k in config_keys:
                config_new[k] = kwargs.pop(k)

        return cls(config_new)

    # we don't show `__getattr__` to type checkers so missing attributes cause errors
    if not TYPE_CHECKING:

        def __getattr__(self, name: str) -> Any:
            try:
                return self.config_dict[name]
            except KeyError:
                try:
                    return config_defaults[name]
                except KeyError:
                    raise AttributeError(f'Config has no attribute {name!r}') from None

    def core_config(self, obj: Any) -> core_schema.CoreConfig:
        """
        Create a pydantic-core config, `obj` is just used to populate `title` if not set in config.

        Pass `obj=None` if you do not want to attempt to infer the `title`.

        We don't use getattr here since we don't want to populate with defaults.
        """
        core_config = core_schema.CoreConfig(
            **core_schema.dict_not_none(
                title=self.config_dict.get('title') or (obj and obj.__name__),
                extra_fields_behavior=self.config_dict.get('extra'),
                allow_inf_nan=self.config_dict.get('allow_inf_nan'),
                populate_by_name=self.config_dict.get('populate_by_name'),
                str_strip_whitespace=self.config_dict.get('str_strip_whitespace'),
                str_to_lower=self.config_dict.get('str_to_lower'),
                str_to_upper=self.config_dict.get('str_to_upper'),
                strict=self.config_dict.get('strict'),
                ser_json_timedelta=self.config_dict.get('ser_json_timedelta'),
                ser_json_bytes=self.config_dict.get('ser_json_bytes'),
                from_attributes=self.config_dict.get('from_attributes'),
                loc_by_alias=self.config_dict.get('loc_by_alias'),
                revalidate_instances=self.config_dict.get('revalidate_instances'),
                validate_default=self.config_dict.get('validate_default'),
                str_max_length=self.config_dict.get('str_max_length'),
                str_min_length=self.config_dict.get('str_min_length'),
                hide_input_in_errors=self.config_dict.get('hide_input_in_errors'),
            )
        )
        return core_config

    def __repr__(self):
        c = ', '.join(f'{k}={v!r}' for k, v in self.config_dict.items())
        return f'ConfigWrapper({c})'


config_defaults = ConfigDict(
    title=None,
    str_to_lower=False,
    str_to_upper=False,
    str_strip_whitespace=False,
    str_min_length=0,
    str_max_length=None,
    # let the model / dataclass decide how to handle it
    extra=None,
    frozen=False,
    populate_by_name=False,
    use_enum_values=False,
    validate_assignment=False,
    arbitrary_types_allowed=False,
    from_attributes=False,
    loc_by_alias=True,
    alias_generator=None,
    ignored_types=(),
    allow_inf_nan=True,
    json_schema_extra=None,
    strict=False,
    revalidate_instances='never',
    ser_json_timedelta='iso8601',
    ser_json_bytes='utf8',
    validate_default=False,
    validate_return=False,
    protected_namespaces=('model_',),
    hide_input_in_errors=False,
)


def prepare_config(config: ConfigDict | dict[str, Any] | type[Any] | None) -> ConfigDict:
    """
    Create a `ConfigDict` instance from an existing dict, a class (e.g. old class-based config) or None.
    """
    if config is None:
        return ConfigDict()

    if not isinstance(config, dict):
        warnings.warn(DEPRECATION_MESSAGE, DeprecationWarning)
        config = {k: getattr(config, k) for k in dir(config) if not k.startswith('__')}

    config_dict = cast(ConfigDict, config)
    check_deprecated(config_dict)
    return config_dict


config_keys = set(ConfigDict.__annotations__.keys())


V2_REMOVED_KEYS = {
    'allow_mutation',
    'error_msg_templates',
    'fields',
    'getter_dict',
    'smart_union',
    'underscore_attrs_are_private',
    'json_loads',
    'json_dumps',
    'json_encoders',
    'copy_on_model_validation',
    'post_init_call',
}
V2_RENAMED_KEYS = {
    'allow_population_by_field_name': 'populate_by_name',
    'anystr_lower': 'str_to_lower',
    'anystr_strip_whitespace': 'str_strip_whitespace',
    'anystr_upper': 'str_to_upper',
    'keep_untouched': 'ignored_types',
    'max_anystr_length': 'str_max_length',
    'min_anystr_length': 'str_min_length',
    'orm_mode': 'from_attributes',
    'schema_extra': 'json_schema_extra',
    'validate_all': 'validate_default',
}


def check_deprecated(config_dict: ConfigDict) -> None:
    """
    Check for deprecated config keys and warn the user.
    """
    deprecated_removed_keys = V2_REMOVED_KEYS & config_dict.keys()
    deprecated_renamed_keys = V2_RENAMED_KEYS.keys() & config_dict.keys()
    if deprecated_removed_keys or deprecated_renamed_keys:
        renamings = {k: V2_RENAMED_KEYS[k] for k in sorted(deprecated_renamed_keys)}
        renamed_bullets = [f'* {k!r} has been renamed to {v!r}' for k, v in renamings.items()]
        removed_bullets = [f'* {k!r} has been removed' for k in sorted(deprecated_removed_keys)]
        message = '\n'.join(['Valid config keys have changed in V2:'] + renamed_bullets + removed_bullets)
        warnings.warn(message, UserWarning)
