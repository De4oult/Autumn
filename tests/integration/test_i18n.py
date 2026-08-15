import contextlib
import io
import unittest
from pathlib import Path

from tests.support import asgi_request, reset_framework_state, run_async

from autumn.configuration import LocalizationConfiguration
from autumn.controller import REST, get
from autumn.core.app import Autumn
from autumn.i18n import I18n, Locale
from autumn.resources import Resources


FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'


class I18nIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_framework_state()

    def test_app_injects_i18n_from_accept_language_header(self) -> None:
        class ProjectLocalizationConfiguration(LocalizationConfiguration):
            supported_locales = ('en', 'ru')
            default_locale = 'en'
            locales = Resources(FIXTURES / 'locales')

        app = Autumn()

        @REST(prefix = '/hello')
        class HelloController:
            @get('/')
            async def index(self, i18n: I18n, locale: Locale) -> dict:
                return {
                    'locale'  : locale.code,
                    'message' : i18n.t('hello.message', name = 'Autumn')
                }

        response = run_async(
            asgi_request(
                app,
                path = '/hello',
                headers = {'accept-language': 'ru-RU, en;q=0.5'}
            )
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json(), {
            'locale'  : 'ru',
            'message' : 'Привет, Autumn'
        })

    def test_i18n_falls_back_to_default_locale(self) -> None:
        class ProjectLocalizationConfiguration(LocalizationConfiguration):
            supported_locales = ('en', 'ru')
            default_locale = 'en'
            locales = Resources(FIXTURES / 'locales_default')

        app = Autumn()

        @REST(prefix = '/hello')
        class HelloController:
            @get('/')
            async def index(self, i18n: I18n, locale: Locale) -> dict:
                return {
                    'locale'  : locale.code,
                    'message' : i18n.t('hello.message')
                }

        response = run_async(asgi_request(app, path = '/hello'))

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json(), {
            'locale'  : 'en',
            'message' : 'Hello'
        })

    def test_i18n_warns_and_falls_back_to_key_when_locale_file_is_missing(self) -> None:
        class ProjectLocalizationConfiguration(LocalizationConfiguration):
            supported_locales = ('fr',)
            default_locale = 'fr'
            locales = Resources(FIXTURES / 'missing_locales')

        app = Autumn()

        @REST(prefix = '/hello')
        class HelloController:
            @get('/')
            async def index(self, i18n: I18n) -> dict:
                return {'message': i18n.t('hello.message')}

        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            response = run_async(asgi_request(app, path = '/hello'))

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json(), {'message': 'hello.message'})
        self.assertIn("Localization resource for locale 'fr' was not found", output.getvalue())

    def test_i18n_supports_pluralization_with_custom_rules(self) -> None:
        def russian_plural(count: int | float) -> str:
            value = abs(int(count))

            if value % 10 == 1 and value % 100 != 11:
                return 'one'

            if 2 <= value % 10 <= 4 and not 12 <= value % 100 <= 14:
                return 'few'

            return 'many'

        class ProjectLocalizationConfiguration(LocalizationConfiguration):
            supported_locales = ('en', 'ru')
            default_locale = 'en'
            locales = Resources(FIXTURES / 'locales')
            plural_rules = {
                'ru': russian_plural
            }

        app = Autumn()

        @REST(prefix = '/cart')
        class CartController:
            @get('/')
            async def index(self, i18n: I18n) -> dict:
                return {
                    'one'  : i18n.plural('cart.items', 1),
                    'few'  : i18n.plural('cart.items', 2),
                    'many' : i18n.plural('cart.items', 5)
                }

        response = run_async(
            asgi_request(
                app,
                path = '/cart',
                headers = {'accept-language': 'ru'}
            )
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json(), {
            'one'  : '1 товар',
            'few'  : '2 товара',
            'many' : '5 товаров'
        })
