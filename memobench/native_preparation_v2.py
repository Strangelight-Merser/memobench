"""Read-only preparation of approved native runs; no transport or model calls."""
from pathlib import Path
import shlex
import sys
from .adapters_v2.factory import PRODUCTS, review_native_settings
from .data_v2 import validate_release, load_dataset
from .runner_v2 import ROOT, hash_inventory, save, select_cases


def prepare(recipe, out, *, ssh_config, acceptances, dataset=None):
    expected = {'schema_version', 'dataset', 'split', 'products', 'purpose'}
    if not expected.issubset(recipe) or set(recipe) - expected - {'case_selection'} or recipe['schema_version'] != 'native-run-recipe-1':
        raise ValueError('native preparation recipe required; recipe is not a run config')
    if (recipe['split'] != 'test' or recipe['purpose'] not in ('frozen_evaluation', 'internal_evaluation')
            or not isinstance(recipe['products'], list) or not recipe['products']
            or len(set(recipe['products'])) != len(recipe['products'])
            or set(recipe['products']) - set(PRODUCTS)):
        raise ValueError('invalid frozen native scope')
    if set(acceptances) - set(recipe['products']):
        raise ValueError('acceptance supplied for unplanned product')
    output = Path(out).resolve()
    if output.exists():
        raise ValueError('preparation needs a new output directory')
    data = Path(dataset).resolve() if dataset is not None else (ROOT / recipe['dataset']).resolve()
    if output.is_relative_to(data):
        raise ValueError('preparation output must be outside the approved dataset')
    config_path = Path(ssh_config).resolve()
    validation = validate_release(data)
    episodes = load_dataset(data, recipe['split'])
    if 'case_selection' in recipe:
        episodes = select_cases(episodes, recipe['case_selection'])
    inventory = hash_inventory(data, [path for path in data.iterdir() if path.is_file()])
    validation = dict(validation, content_sha256=inventory['sha256'])
    approved = (validation['release_status'] == 'accepted' or (validation['release_status'] == 'accepted_internal'
                and validation.get('usage_scope') == 'internal_evaluation_only' and recipe['purpose'] == 'internal_evaluation'))
    blockers = []
    if not approved:
        blockers.append({'code': 'data_approval_required', 'release_status': validation['release_status'],
                         'pending_n_story': validation.get('pending_n_story'), 'license_status': validation.get('license_status')})
    if not episodes:
        blockers.append({'code': 'approved_test_empty'})
    if any(action['operation'] != 'create' for episode in episodes for gold in episode.golds for action in gold.expected_actions):
        blockers.append({'code': 'native_render_unsupported'})
    configs = {}
    import hashlib
    for product in recipe['products']:
        acceptance = acceptances.get(product)
        if acceptance is None:
            blockers.append({'product': product, 'code': 'current_raw_probe_required'})
            continue
        acceptance = Path(acceptance).resolve()
        if not config_path.is_file():
            blockers.append({'product': product, 'code': 'ssh_configuration_missing'})
            continue
        if not acceptance.is_file():
            blockers.append({'product': product, 'code': 'acceptance_file_missing'})
            continue
        settings = {'ssh_config': str(config_path), 'purpose': recipe['purpose'],
            'acceptance': str(acceptance), 'acceptance_sha256': hashlib.sha256(acceptance.read_bytes()).hexdigest(),
            'bridge_sha256': hashlib.sha256((ROOT/'tools/native_vm_product.py').read_bytes()).hexdigest(),
            'config_sha256': hashlib.sha256(config_path.read_bytes()).hexdigest(), 'dataset_sha256': inventory['sha256']}
        if not approved:
            continue
        try:
            review_native_settings(product, settings, validation)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            # Known preflight codes contain no private response or file data.
            code = str(exc) if isinstance(exc, ValueError) and str(exc).startswith('native_') else type(exc).__name__
            blockers.append({'product': product, 'code': 'acceptance_not_verified', 'detail': code})
            continue
        configs[product] = {'dataset': str(data), 'split': recipe['split'], 'mode': 'native_agent',
                            'execution': 'online', 'adapter': product, 'native': settings}
        if 'case_selection' in recipe:
            configs[product]['case_selection'] = recipe['case_selection']
    planned = [{'episode_id': episode.episode_id, 'variant_id': episode.variant_id, 'story_id': episode.story_id,
                'observations': len(episode.observations), 'queries': len(episode.probes),
                'sessions': len(episode.session_ids),
                'artifact_queries': sum(bool(gold.expected_actions) for gold in episode.golds)} for episode in episodes]
    count = len(recipe['products'])
    plan = {'status': 'blocked' if blockers else 'ready_for_scope_and_budget_review',
        'no_transport_created': True, 'model_api_calls': 0, 'execution': 'plan_only',
        'evaluation_scope': validation.get('usage_scope'), 'review_method': validation.get('review_method'),
        'unseen_holdout_claim': False, 'public_license_granted': validation.get('license_status') == 'accepted',
        'recipe': recipe, 'dataset': str(data), 'dataset_validation': validation, 'dataset_sha256': inventory['sha256'],
        'products': recipe['products'], 'planned_cases_per_product': planned,
        'independent_stories': len({episode.story_id for episode in episodes}),
        'episode_variants_per_product': len(episodes), 'n_case': count*len(episodes),
        'product_calls': count*sum(row['observations']+row['queries'] for row in planned),
        'lifecycle_calls': count*sum(2+2*row['sessions'] for row in planned),
        'artifact_inspection_calls': count*sum(2*row['artifact_queries'] for row in planned),
        'provider_requests': None, 'estimated_cost': None, 'blockers': blockers,
        'configs': {}, 'run_commands': [], 'publish_ranking': False}
    output.mkdir(parents=True)
    if not blockers:
        for product, config in configs.items():
            path = output/(product+'.json')
            save(output, path.name, config)
            plan['configs'][product] = str(path)
            plan['run_commands'].append(shlex.join([sys.executable, '-m', 'memobench.cli_v2', 'run',
                '--config', str(path), '--out', str(output/('run-'+product)), '--live']))
    save(output, 'plan.json', plan)
    return plan
