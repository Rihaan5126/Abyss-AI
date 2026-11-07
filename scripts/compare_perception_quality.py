"""Matched exploratory missions: old vision, new vision and ideal sensing. No downloads."""

import argparse
from dataclasses import replace
import json
from pathlib import Path

from abyss.config import load_config
from abyss.evaluation.metrics import mission_metrics
from abyss.fathomnet_perception import build_kit
from abyss.planners import PLANNERS
from abyss.run_mission import run_mission, validate_mission_log
from perception import Perception
from perception.embed import CachedEncoder, DinoV2Encoder
from perception.quality import mission_analysis


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',required=True)
    p.add_argument('--old-artifact',default='data/perception-expanded')
    p.add_argument('--new-artifact',default='data/perception-quality')
    p.add_argument('--model-cache',default='.cache/huggingface')
    p.add_argument('--embedding-cache',default='.cache/embeddings')
    p.add_argument('--output',default='results/perception-quality-missions.json')
    args=p.parse_args()
    if Path(args.output).exists():p.error('Choose a new output file to preserve earlier experiments')
    encoder=CachedEncoder(DinoV2Encoder(cache_dir=args.model_cache,offline=True),args.embedding_cache)
    models={name:Perception.load(path,encoder) for name,path in
            [('old',args.old_artifact),('new',args.new_artifact)]}
    kits={name:build_kit(model,args.manifest) for name,model in models.items()}
    if kits['old']['image_pool'].categories!=kits['new']['image_pool'].categories:
        raise ValueError('Both models must use the same category definitions')
    base=load_config();rows=[]
    for scenario,rho in [('ridge',1.),('reversed',1.),('random',0.)]:
        config=replace(base,scenario=scenario,rho=rho,n_categories=len(kits['new']['image_pool'].categories))
        for seed in (1000,1001):
            for planner in ('frontier','abyss'):
                for mode in ('ideal','old','new'):
                    cfg=replace(config,perception_mode='ideal' if mode=='ideal' else 'real')
                    log,reveal=run_mission(cfg,PLANNERS[planner](),seed,**({} if mode=='ideal' else kits[mode]))
                    validate_mission_log(log)
                    row={'scenario':scenario,'seed':seed,'planner':planner,'mode':mode,**mission_metrics(log,reveal)}
                    if mode!='ideal':row['vision']=mission_analysis(reveal)
                    rows.append(row)
                    print(f'{scenario} {seed} {planner} {mode}: true {row["distinct_categories"]}, perceived {row["perceived_categories"]}, safe {row["safe_return"]}',flush=True)
    result={'purpose':'Exploratory matched missions, two seeds per scenario; not the frozen 6300-mission benchmark',
            'category_count':config.n_categories,'neighbors':{k:v.neighbors for k,v in models.items()},
            'artifact_metadata':{k:json.loads((Path(path)/'metadata.json').read_text()) for k,path in
                                 [('old',args.old_artifact),('new',args.new_artifact)]},'missions':rows}
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
