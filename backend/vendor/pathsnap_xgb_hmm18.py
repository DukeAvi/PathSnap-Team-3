"""Shared-eighteen XGBoost Bayesian search and directed-network Viterbi decoding."""
from pathlib import Path, PurePosixPath
from dataclasses import dataclass
from time import perf_counter
from hashlib import sha256
import io, json, zipfile, shutil, gc, importlib.metadata
import numpy as np
import pandas as pd
import joblib, optuna
from xgboost import XGBClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, log_loss, confusion_matrix
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from pyproj import Transformer

FEATURES = ['distance_m', 'distance_rank', 'heading_difference_deg', 'projection_fraction', 'segment_length_m', 'displacement_m', 'heading_valid', 'dt_s', 'speed_mps', 'distance_to_from_m', 'distance_to_to_m', 'from_out_degree', 'to_in_degree', 'from_in_degree', 'to_out_degree', 'candidate_count', 'distance_gap_to_nearest_m', 'acceleration_mps2']
BASE_PARAMS = dict(objective='binary:logistic', eval_metric='logloss', n_estimators=200,
                   learning_rate=.05, max_depth=6, min_child_weight=10, reg_lambda=1.,
                   tree_method='hist', random_state=42, n_jobs=4)
MAX_GAP = 30.
SEARCH_LIMIT = 3000.
JITTER_M = 15.
CONTINUITY_SPEED = 80.
CONTINUITY_SLACK = 150.

def save_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False, default=str), encoding='utf-8')

def archive_member(z, leaf):
    names = [n for n in z.namelist() if PurePosixPath(n).name == leaf]
    if len(names) != 1:
        raise ValueError(f'Expected exactly one {leaf}, found {len(names)}')
    return names[0]

@dataclass
class Dataset:
    candidates: pd.DataFrame
    observations: pd.DataFrame

def load_shared(path, features=None):
    features = FEATURES if features is None else features
    with zipfile.ZipFile(path) as z:
        protocol = json.loads(z.read(archive_member(z,'shared_protocol.json')))
        if protocol['features'] != features:
            raise ValueError('Feature order differs from requested feature protocol')
        with np.load(io.BytesIO(z.read(archive_member(z,'shared_inputs.npz'))), allow_pickle=False) as a:
            assert a['features'].tolist() == features
            datasets = []
            for split, prefix in [('train','train'),('student_test','test')]:
                x = a[f'X_{prefix}_raw']
                assert x.ndim == 2 and x.shape[1] == len(features) and np.isfinite(x).all()
                c = pd.DataFrame(x, columns=features)
                c['label'] = a[f'y_{prefix}']
                for key in ['trip_id','observation_id','arc_id']:
                    c[key] = a[f'{prefix}_{key}']
                c['trip_id'] = c.trip_id.astype(str)
                obs = pd.read_csv(io.BytesIO(z.read(archive_member(z,f'{split}_observations.csv.gz'))), compression='gzip', dtype={'trip_id':str})
                assert obs.observation_id.is_unique and not c.duplicated(['observation_id','arc_id']).any()
                ref = obs.set_index('observation_id')
                assert (c.observation_id.map(ref.trip_id) == c.trip_id).all()
                assert np.array_equal(c.label, (c.arc_id == c.observation_id.map(ref.reference_arc_id)).astype('int8'))
                counts = c.groupby('observation_id').label.agg(['count','sum']).reindex(ref.index, fill_value=0)
                assert (counts['sum'] <= 1).all()
                assert np.array_equal(counts['sum'] > 0, ref.reference_present)
                assert np.array_equal(counts['count'], ref.candidate_count)
                datasets.append(Dataset(c,obs))
            row_folds = a['fold_id'].copy()
        assignments = pd.read_csv(io.BytesIO(z.read(archive_member(z,'fold_assignments.csv'))), dtype={'trip_id':str})
        mapping = assignments.set_index('trip_id').fold
        assert len(assignments) == 80 and assignments.trip_id.is_unique
        assert set(mapping) == {1,2,3,4,5}
        train, test = datasets
        assert train.observations.trip_id.nunique() == 80 and test.observations.trip_id.nunique() == 10
        assert not set(train.observations.trip_id) & set(test.observations.trip_id)
        assert set(mapping.index) == set(train.observations.trip_id)
        assert np.array_equal(train.candidates.trip_id.map(mapping), row_folds)
        train.observations['fold'] = train.observations.trip_id.map(mapping)
        folds = {}
        for fold in range(1,6):
            with np.load(io.BytesIO(z.read(archive_member(z,f'fold_{fold}_indices.npz'))), allow_pickle=False) as a:
                fit, valid = a['fit_idx'].copy(), a['valid_idx'].copy()
            assert np.array_equal(fit, np.flatnonzero(row_folds != fold))
            assert np.array_equal(valid, np.flatnonzero(row_folds == fold))
            folds[fold] = (fit, valid)
        assert len(train.candidates) == protocol['train_candidates']
        assert len(test.candidates) == protocol['test_candidates']
    return train, test, folds, assignments, protocol

def observation_predictions(ds, p):
    p = np.asarray(p, dtype=float)
    assert p.shape == (len(ds.candidates),) and np.isfinite(p).all() and ((p>=0)&(p<=1)).all()
    s = ds.candidates[['observation_id','arc_id','distance_rank']].copy()
    s['probability'] = p
    best = s.sort_values(['observation_id','probability','distance_rank','arc_id'], ascending=[True,False,True,True], kind='stable').drop_duplicates('observation_id')
    o = ds.observations.merge(best[['observation_id','arc_id','probability']], on='observation_id', how='left', validate='one_to_one')
    o = o.rename(columns={'arc_id':'predicted_arc_id','probability':'predicted_probability'})
    o['predicted_arc_id'] = o.predicted_arc_id.fillna(-1).astype('int64')
    o['correct'] = o.predicted_arc_id == o.reference_arc_id
    return o

def candidate_metrics(ds, p):
    y = ds.candidates.label.to_numpy()
    pred = np.asarray(p) >= .5
    return {'Accuracy':accuracy_score(y,pred), 'Precision':precision_score(y,pred,zero_division=0),
            'Recall':recall_score(y,pred,zero_division=0), 'F1':f1_score(y,pred,zero_division=0),
            'Macro F1':f1_score(y,pred,average='macro',labels=[0,1],zero_division=0),
            'Log Loss':log_loss(y,np.column_stack([1-p,p]),labels=[0,1])}

def top1(ds, p):
    return float(observation_predictions(ds,p).correct.mean())

def subset(ds, indices):
    c = ds.candidates.iloc[indices]
    return Dataset(c, ds.observations[ds.observations.trip_id.isin(c.trip_id.unique())])

def fit_predict(params, fit, valid):
    scaler = StandardScaler()
    start = perf_counter()
    x = scaler.fit_transform(fit.candidates[FEATURES])
    model = XGBClassifier(**params)
    model.fit(x, fit.candidates.label)
    training = perf_counter()-start
    start = perf_counter()
    p = model.predict_proba(scaler.transform(valid.candidates[FEATURES]))[:,1]
    inference = perf_counter()-start
    return model, scaler, p, training, inference

def cv_scores(ds, folds, params, cache, trial=None):
    """All probabilities are strictly held-out w.r.t. classifier fitting."""
    key = sha256(json.dumps(params,sort_keys=True).encode()).hexdigest()[:16]
    cache = Path(cache); cache.mkdir(parents=True,exist_ok=True)
    p = np.full(len(ds.candidates),np.nan,dtype='float32'); rows=[]
    for f,(fit_idx,valid_idx) in folds.items():
        path = cache/f'{key}_fold{f}.npz'
        fit, valid = subset(ds,fit_idx), subset(ds,valid_idx)
        if 'fold' in ds.observations:
            # Preserve even a validation trip with no candidate rows at all.
            valid = Dataset(valid.candidates, ds.observations[ds.observations['fold']==f])
        assert not set(fit.candidates.trip_id) & set(valid.candidates.trip_id)
        if path.exists():
            with np.load(path,allow_pickle=False) as a:
                assert np.array_equal(a['indices'],valid_idx)
                probs=a['p']; tr=float(a['train_seconds']); inf=float(a['inference_seconds'])
        else:
            model,scaler,probs,tr,inf=fit_predict(params,fit,valid)
            np.savez_compressed(path,p=probs,indices=valid_idx,train_seconds=tr,inference_seconds=inf)
            del model,scaler; gc.collect()
        p[valid_idx]=probs
        rows.append({'Fold':f,**candidate_metrics(valid,probs), 'Top-1 Accuracy':top1(valid,probs), 'Train Time':tr,'Inference Time':inf})
        if trial is not None:
            trial.report(float(np.mean([r['Top-1 Accuracy'] for r in rows])),step=f)
            if trial.should_prune(): raise optuna.TrialPruned()
    assert np.isfinite(p).all()
    return p,pd.DataFrame(rows)

def tune_xgboost(train, folds, out, n_trials=12, n_jobs=4):
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    search={'n_estimators':[120,500,20], 'learning_rate':[.02,.15], 'max_depth':[3,9],
            'min_child_weight':[2.,40.], 'subsample':[.7,1.], 'colsample_bytree':[.7,1.],
            'reg_lambda':[.1,20.], 'reg_alpha':[0.,3.], 'gamma':[0.,2.]}
    save_json(out/'xgboost_search_space.json',search)
    baseline={**BASE_PARAMS,'n_jobs':n_jobs}
    base_p,base_cv=cv_scores(train,folds,baseline,out/'cv_cache')
    base_cv.to_csv(out/'baseline_cv_fold_metrics.csv',index=False)
    study=optuna.create_study(direction='maximize',sampler=optuna.samplers.TPESampler(seed=42,n_startup_trials=5),
                              pruner=optuna.pruners.MedianPruner(n_startup_trials=5,n_warmup_steps=2))
    study.enqueue_trial(dict(n_estimators=200,learning_rate=.05,max_depth=6,min_child_weight=10.,
                             subsample=1.,colsample_bytree=1.,reg_lambda=1.,reg_alpha=0.,gamma=0.))
    def objective(t):
        params={**baseline,'n_estimators':t.suggest_int('n_estimators',120,500,step=20),
                'learning_rate':t.suggest_float('learning_rate',.02,.15,log=True),
                'max_depth':t.suggest_int('max_depth',3,9),
                'min_child_weight':t.suggest_float('min_child_weight',2.,40.,log=True),
                'subsample':t.suggest_float('subsample',.7,1.),'colsample_bytree':t.suggest_float('colsample_bytree',.7,1.),
                'reg_lambda':t.suggest_float('reg_lambda',.1,20.,log=True),
                'reg_alpha':t.suggest_float('reg_alpha',0.,3.),'gamma':t.suggest_float('gamma',0.,2.)}
        _, metrics=cv_scores(train,folds,params,out/'cv_cache',t)
        return float(metrics['Top-1 Accuracy'].mean())
    def checkpoint(s,t): s.trials_dataframe().to_csv(out/'xgboost_bayesian_trials.csv',index=False)
    start=perf_counter(); study.optimize(objective,n_trials=n_trials,callbacks=[checkpoint])
    best={**baseline,**study.best_params}
    p,cv=cv_scores(train,folds,best,out/'cv_cache')
    # Explicitly retain the baseline if the search did not improve its CV objective.
    if cv['Top-1 Accuracy'].mean() < base_cv['Top-1 Accuracy'].mean(): best,p,cv=baseline,base_p,base_cv
    cv.to_csv(out/'selected_cv_fold_metrics.csv',index=False)
    np.save(out/'baseline_oof_probabilities.npy',base_p)
    np.save(out/'selected_oof_probabilities.npy',p)
    save_json(out/'selected_xgboost_parameters.json',best)
    save_json(out/'optimisation_summary.json',{'seconds':perf_counter()-start,'trials':len(study.trials),
        'objective':'unweighted mean fixed-five-fold observation Top-1',
        'interpretation':'Model-selection CV scores; not nested-CV unbiased performance estimates.'})
    return best,base_p,p,base_cv,cv,study

def load_existing(path, features=None):
    features = FEATURES if features is None else features
    """Read the user's own trusted model bundle; never extract arbitrary paths."""
    with zipfile.ZipFile(path) as z:
        config=json.loads(z.read(archive_member(z,'model_config.json')))
        if config['features'] != features: raise ValueError('Saved model features mismatch')
        model=XGBClassifier(); model.load_model(bytearray(z.read(archive_member(z,'xgboost_model.ubj'))))
        scaler=joblib.load(io.BytesIO(z.read(archive_member(z,'final_scaler.joblib'))))
        saved=pd.read_csv(io.BytesIO(z.read(archive_member(z,'model_comparison.csv')))).iloc[0].to_dict()
    return model,scaler,saved

def build_lattices(ds, network_zip, split, cache):
    """Label-free lattice geometry. Only .nodes and .arcs are opened, never .route."""
    cache=Path(cache); cache.mkdir(parents=True,exist_ok=True)
    result=[]
    with zipfile.ZipFile(network_zip) as z:
        for trip, obs in ds.observations.groupby('trip_id',sort=True):
            path=cache/f'{split}_{trip}.npz'
            if path.exists():
                with np.load(path,allow_pickle=False) as a: lattice={k:a[k].copy() for k in a.files}
                result.append(lattice); continue
            start=perf_counter()
            obs=obs.sort_values(['timestamp','observation_id'],kind='stable')
            c=ds.candidates[ds.candidates.trip_id==trip].sort_values(['observation_id','distance_rank','arc_id'],kind='stable')
            def read_network(ext,cols):
                names=[n for n in z.namelist() if n.replace('\\','/').endswith(f'/{split}/{trip}/{trip}.{ext}')]
                if len(names)!=1: raise ValueError(f'Missing or ambiguous {split}/{trip}.{ext}')
                a=np.loadtxt(io.BytesIO(z.read(names[0])),ndmin=2)
                assert a.shape[1]==cols and np.isfinite(a).all()
                return a
            nodes=read_network('nodes',2); raw_arcs=read_network('arcs',2)
            assert np.equal(raw_arcs,np.floor(raw_arcs)).all()
            arcs=raw_arcs.astype('int64'); assert arcs.min()>=0 and arcs.max()<len(nodes)
            lon,lat=obs[['longitude','latitude']].median().to_numpy()
            zone=min(60,max(1,int((lon+180)//6)+1)); epsg=(32600 if lat>=0 else 32700)+zone
            tf=Transformer.from_crs(4326,epsg,always_xy=True)
            xy=np.column_stack(tf.transform(nodes[:,0],nodes[:,1]))
            gps=np.column_stack(tf.transform(obs.longitude.to_numpy(),obs.latitude.to_numpy()))
            length=np.linalg.norm(xy[arcs[:,1]]-xy[arcs[:,0]],axis=1)
            ca=c.arc_id.to_numpy(dtype=int)
            assert (ca>=0).all() and (ca<len(arcs)).all()
            if not np.allclose(length[ca],c.segment_length_m,rtol=1e-4,atol=.05):
                raise ValueError(f'{trip}: network geometry does not match feature archive')
            # Collapse parallel node pairs by minimum length; sparse constructors otherwise sum them.
            active=np.flatnonzero(length>1e-6)
            order=active[np.lexsort((length[active],arcs[active,1],arcs[active,0]))]
            unique=np.r_[True,np.any(arcs[order[1:]]!=arcs[order[:-1]],axis=1)]
            edges=order[unique]
            graph=csr_matrix((length[edges],(arcs[edges,0],arcs[edges,1])),shape=(len(nodes),len(nodes)))
            obs_ids=obs.observation_id.to_numpy(); positions={v:i for i,v in enumerate(obs_ids)}
            idx=np.full((len(obs),8),-1,dtype='int64'); arc=np.full_like(idx,-1); frac=np.zeros_like(idx,dtype=float)
            for oid,group in c.groupby('observation_id',sort=False):
                r=positions[oid]; k=len(group); assert k<=8
                idx[r,:k]=group.index; arc[r,:k]=group.arc_id; frac[r,:k]=group.projection_fraction
            dt=np.r_[0.,np.diff(obs.timestamp.to_numpy())]
            displacement=np.r_[0.,np.linalg.norm(np.diff(gps,axis=0),axis=1)]
            routes=np.full((len(obs),8,8),np.inf,dtype='float32')
            # Query each needed source endpoint once, with a bounded directed Dijkstra search.
            requested={}
            for t in range(1,len(obs)):
                if not 0<dt[t]<=MAX_GAP: continue
                aa=arc[t-1][idx[t-1]>=0]; bb=arc[t][idx[t]>=0]
                for source in np.unique(arcs[aa,1]):
                    requested.setdefault(int(source),set()).update(map(int,arcs[bb,0]))
            distances={}
            for source,targets in requested.items():
                d=dijkstra(graph,directed=True,indices=source,limit=SEARCH_LIMIT)
                distances[source]={target:float(d[target]) for target in targets}
            for t in range(1,len(obs)):
                if not 0<dt[t]<=MAX_GAP: continue
                for i in np.flatnonzero(idx[t-1]>=0):
                    a=arc[t-1,i]; fa=frac[t-1,i]
                    for j in np.flatnonzero(idx[t]>=0):
                        b=arc[t,j]; fb=frac[t,j]
                        bridge=distances[int(arcs[a,1])][int(arcs[b,0])]
                        dist=(1-fa)*length[a]+bridge+fb*length[b]
                        delta=(fb-fa)*length[a]
                        if a==b and delta>=-JITTER_M: dist=min(dist,max(0.,delta))
                        routes[t,i,j]=dist
            lattice=dict(indices=idx,arcs=arc,obs_ids=obs_ids,dt=dt,displacement=displacement,routes=routes,trip=np.array(str(trip)))
            np.savez_compressed(path,**lattice); result.append(lattice)
            print(f'{split}/{trip}: {len(obs)} observations; graph+lattice {perf_counter()-start:.1f}s',flush=True)
    return result

def decode_lattice(lattice,p,config):
    idx=lattice['indices']; n,k=idx.shape
    emission=np.full((n,k),-np.inf)
    mask=idx>=0; emission[mask]=np.log(np.clip(np.asarray(p)[idx[mask]],1e-9,1.))
    # Candidate probabilities are discriminative emission scores, not claimed generative likelihoods.
    chosen=np.full(n,-1,dtype=int); reasons=np.full(n,'',dtype='<U24')
    segment=[]; back=[]; dp=None
    def finish():
        if not segment: return
        state=int(np.argmax(dp))
        for t,b in zip(reversed(segment),reversed(back)):
            chosen[t]=state; state=int(b[state])
    for t in range(n):
        if not mask[t].any():
            finish(); segment=[]; back=[]; dp=None; reasons[t]='no_candidates'; continue
        reset=dp is None or not 0<lattice['dt'][t]<=MAX_GAP
        if reset:
            finish(); segment=[]; back=[]
            reasons[t]='start' if t==0 else ('gap_reset' if lattice['dt'][t]>MAX_GAP else 'restart')
        else:
            d=lattice['routes'][t]
            allowed=np.isfinite(d)&(d<=config['max_speed_mps']*lattice['dt'][t]+config['slack_m'])
            beta=config['beta_m']+config['beta_displacement']*lattice['displacement'][t]
            trans=np.where(allowed,-np.abs(d-lattice['displacement'][t])/beta,-np.inf)
            scores=dp[:,None]+trans
            prev=np.argmax(scores,axis=0)
            new=emission[t]+scores[prev,np.arange(k)]
            if not np.isfinite(new).any():
                finish(); segment=[]; back=[]; reset=True; reasons[t]='transition_reset'
        if reset:
            dp=emission[t].copy(); prev=np.full(k,-1,dtype=int)
        else: dp=new
        dp-=np.max(dp)
        segment.append(t); back.append(prev)
    finish()
    out=np.full(n,-1,dtype='int64'); valid=chosen>=0
    out[valid]=lattice['arcs'][np.flatnonzero(valid),chosen[valid]]
    return out,reasons

def decode_all(lattices,p,config):
    frames=[]; start=perf_counter()
    for l in lattices:
        arcs,reasons=decode_lattice(l,p,config)
        frames.append(pd.DataFrame({'observation_id':l['obs_ids'],'decoded_arc_id':arcs,'decoder_event':reasons}))
    return pd.concat(frames,ignore_index=True),perf_counter()-start

def continuity(lattices, prediction):
    """Fixed rule for every model: gaps/unmatched pairs count as failures."""
    pred=prediction.set_index('observation_id').predicted_arc_id
    success=0; total=0; eligible=0
    for l in lattices:
        a=pred.reindex(l['obs_ids']).fillna(-1).to_numpy(dtype=int)
        for t in range(1,len(a)):
            total+=1
            if not 0<l['dt'][t]<=MAX_GAP or a[t-1]<0 or a[t]<0: continue
            eligible+=1
            i=np.flatnonzero(l['arcs'][t-1]==a[t-1]); j=np.flatnonzero(l['arcs'][t]==a[t])
            if len(i) and len(j):
                d=l['routes'][t,i[0],j[0]]
                success+=int(np.isfinite(d) and d<=CONTINUITY_SPEED*l['dt'][t]+CONTINUITY_SLACK)
    return {'Route Continuity':success/total if total else 0.,'Continuity Eligible':success/eligible if eligible else 0.,
            'Continuity Pair Count':total,'Continuity Eligible Pair Count':eligible}

def sequence_metrics(pred):
    correct=pred.predicted_arc_id==pred.reference_arc_id
    grouped=correct.groupby(pred.trip_id)
    return {'Pointwise Accuracy':float(correct.mean()), 'Mean Trip Accuracy':float(grouped.mean().mean()),
            'Exact Observation Sequence Accuracy':float(grouped.all().mean()),
            'Unmatched Rate':float((pred.predicted_arc_id<0).mean())}

def decoder_objective(train,decoded,assignments):
    o=train.observations.merge(decoded,on='observation_id',validate='one_to_one')
    o['correct']=o.decoded_arc_id==o.reference_arc_id
    mapping=assignments.set_index('trip_id').fold
    return float(o.groupby(o.trip_id.map(mapping)).correct.mean().mean())

def tune_decoder(train,lattices,p,assignments,out,n_trials=20):
    out=Path(out)
    study=optuna.create_study(direction='maximize',sampler=optuna.samplers.TPESampler(seed=43,n_startup_trials=5))
    def objective(t):
        config={'beta_m':t.suggest_float('beta_m',10.,200.,log=True),
                'beta_displacement':t.suggest_float('beta_displacement',0.,.5),
                'max_speed_mps':t.suggest_float('max_speed_mps',20.,80.),
                'slack_m':t.suggest_float('slack_m',30.,150.)}
        decoded,seconds=decode_all(lattices,p,config)
        t.set_user_attr('decode_seconds',seconds)
        return decoder_objective(train,decoded,assignments)
    def checkpoint(s,t): s.trials_dataframe().to_csv(out/'decoder_bayesian_trials.csv',index=False)
    study.optimize(objective,n_trials=n_trials,callbacks=[checkpoint])
    config=study.best_params
    save_json(out/'decoder_config.json',{**config,'max_gap_s':MAX_GAP,'jitter_m':JITTER_M,
        'search_limit_m':SEARCH_LIMIT,'emission':'log clipped positive-class probability',
        'missing_policy':'unmatched -1; reset on long gaps or all-invalid transitions'})
    return config,study

def export_comparison(train,test,folds,assignments,baseline_cv,selected_cv,baseline_p,selected_p,
                      train_lattices,test_lattices,decoder_config,baseline_model,baseline_scaler,selected_model,selected_scaler,out):
    out=Path(out); rows=[]; cv_rows=[]
    for name,model,scaler,cv,oof in [('Untuned XGBoost',baseline_model,baseline_scaler,baseline_cv,baseline_p),
                                   ('Selected XGBoost',selected_model,selected_scaler,selected_cv,selected_p)]:
        start=perf_counter(); p=model.predict_proba(scaler.transform(test.candidates[FEATURES]))[:,1]; pred_seconds=perf_counter()-start
        pred=observation_predictions(test,p)
        row={'Model':name,'CV Macro F1':float(cv['Macro F1'].mean()),'CV Top-1':float(cv['Top-1 Accuracy'].mean()),
             'Student-test Top-1':float(pred.correct.mean()),**candidate_metrics(test,p),**sequence_metrics(pred),
             **continuity(test_lattices,pred),'Probability Inference Time':pred_seconds,'Decode Time':0.,
             'Inference Time':pred_seconds}
        rows.append(row)
        tag='untuned' if name.startswith('Untuned') else 'selected'
        np.save(out/f'{tag}_student_candidate_probabilities.npy',p)
        pred.to_csv(out/f'{tag}_student_observation_predictions.csv.gz',index=False)
        cm=confusion_matrix(test.candidates.label,p>=.5,labels=[0,1])
        pd.DataFrame(cm,index=['actual_0','actual_1'],columns=['predicted_0','predicted_1']).to_csv(out/f'{tag}_student_confusion_matrix.csv')
        if tag=='selected':
            decoded,seconds=decode_all(test_lattices,p,decoder_config)
            dp=test.observations.merge(decoded,on='observation_id',validate='one_to_one').rename(columns={'decoded_arc_id':'predicted_arc_id'})
            dp['correct']=dp.predicted_arc_id==dp.reference_arc_id
            dp.to_csv(out/'hmm_student_observation_predictions.csv.gz',index=False)
            # Decoder changes a sequence, not candidate class probabilities: no invented decoder Macro F1/log loss.
            rows.append({'Model':'Selected XGBoost + HMM/Viterbi','CV Macro F1':None,'CV Top-1':None,
                         'Student-test Top-1':None,'Macro F1':None,'Log Loss':None,
                         **sequence_metrics(dp),**continuity(test_lattices,dp),
                         'Probability Inference Time':pred_seconds,'Decode Time':seconds,'Inference Time':pred_seconds+seconds})
            decoded_train,_=decode_all(train_lattices,oof,decoder_config)
            oo=train.observations.merge(decoded_train,on='observation_id').rename(columns={'decoded_arc_id':'predicted_arc_id'})
            oo['fold']=oo.trip_id.map(assignments.set_index('trip_id').fold)
            for f,g in oo.groupby('fold'):
                cv_rows.append({'Fold':int(f),**sequence_metrics(g)})
            oo.to_csv(out/'hmm_oof_observation_predictions.csv.gz',index=False)
    comparison=pd.DataFrame(rows)
    comparison.to_csv(out/'final_comparison.csv',index=False)
    pd.DataFrame(cv_rows).to_csv(out/'hmm_cv_fold_metrics.csv',index=False)
    save_json(out/'evaluation_definitions.json',{
        'candidate_classification':'threshold .5; Macro F1 equal mean over classes 0 and 1; log loss from candidate probabilities',
        'top1':'classifier highest probability per observation; ties distance rank then arc ID; all observations included',
        'decoded_pointwise':'Viterbi-selected arc versus same weak reference at every observation, including unmatched',
        'decoder_candidate_metrics':'N/A: decoder does not generate new calibrated candidate probabilities',
        'continuity':'successful directed feasible pairs / ALL consecutive within-trip observation pairs; unmatched/gaps fail',
        'continuity_feasibility':f'0<dt<={MAX_GAP}; directed path <= {CONTINUITY_SPEED}*dt+{CONTINUITY_SLACK} m; jitter {JITTER_M} m',
        'sequence':'fraction of trips with every weak observation arc correct; not alignment against original .route rows',
        'timing':'probability inference includes scaler transform; decoder time excludes one-time graph/lattice construction, reported separately',
        'cv':'same five fixed trip folds; unweighted means; selection CV, not nested evaluation',
        'labels':'geometric weak labels; agreement is not independently verified map-matching accuracy'})
    return comparison
