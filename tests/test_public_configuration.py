"""Personal settings remain usable without appearing in public output."""
import subprocess
from pathlib import Path

import httpx
import pytest

from nepse_trader.ai.providers import AnthropicProvider, OpenRouterProvider
from nepse_trader.config import Settings


@pytest.mark.parametrize('field', ['meroshare_password','meroshare_username','meroshare_dp_id',
                                  'openrouter_api_key','anthropic_api_key'])
def test_sensitive_settings_excluded_from_representations(field):
    sentinel = 'synthetic-private-value-for-publication-test'
    settings = Settings(_env_file=None, **{field: sentinel})
    assert getattr(settings, field) == sentinel
    assert all(sentinel not in output for output in (repr(settings), str(settings),
                                                    str(settings.model_dump()), settings.model_dump_json()))
    assert field not in settings.model_dump()


@pytest.mark.parametrize('provider_class', [OpenRouterProvider, AnthropicProvider])
def test_remote_provider_error_cannot_echo_key_into_logs_or_response(provider_class, caplog):
    key = 'synthetic-provider-secret-' + 'x'*350
    settings = Settings(_env_file=None, openrouter_api_key=key, anthropic_api_key=key,
                        openrouter_models=['example/model'])
    def echo(request):
        return httpx.Response(200, json={'error': {'message': 'Rejected credential: '+key}})
    with httpx.Client(transport=httpx.MockTransport(echo)) as client:
        response = provider_class(settings, client=client).complete('example')
    assert not response.ok and '[REDACTED]' in response.error
    assert key not in response.error and 'synthetic-provider-secret-' not in response.error
    assert 'synthetic-provider-secret-' not in caplog.text


@pytest.mark.parametrize('path', ['.env', '.env.local', 'web/.env.production', '.aws/credentials',
                                 '.mcp.json','data/nepse.db','data/nepse.db-wal','holdings.csv',
                                 'artifacts/ui/dashboard.png','exports/my-holdings.csv'])
def test_personal_files_are_ignored_by_git(path):
    root = Path(__file__).resolve().parent.parent
    result = subprocess.run(['git','check-ignore','--no-index','--quiet',path],cwd=root)
    assert result.returncode == 0, path


def test_public_file_guard_refuses_staged_token_without_printing_it(tmp_path):
    root = Path(__file__).resolve().parent.parent
    subprocess.run(['git','init','--quiet',str(tmp_path)],check=True)
    key = 'ghp_' + 'x'*36
    (tmp_path/'example.py').write_text(f'credential = "{key}"\n')
    subprocess.run(['git','add','example.py'],cwd=tmp_path,check=True)
    result = subprocess.run(['python',str(root/'scripts/check_public_files.py')],cwd=tmp_path,
                            capture_output=True,text=True)
    assert result.returncode == 1
    assert key not in result.stdout + result.stderr
    assert 'possible secret' in result.stdout
    (tmp_path/'example.py').write_text('credential = ""\n')
    subprocess.run(['git','add','example.py'],cwd=tmp_path,check=True)
    assert subprocess.run(['python',str(root/'scripts/check_public_files.py')],cwd=tmp_path,
                          capture_output=True).returncode == 0
