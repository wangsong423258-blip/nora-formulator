"""One calendar/age authority. Dates are civil dates, never UTC timestamps.

Feb 29 anniversaries clamp to Feb 28 in non-leap years. Day-only legacy
inputs have month precision inferred from the Gregorian mean year; callers
with birthdays or completed months must preserve that stronger evidence.
"""
from calendar import monthrange
from datetime import date
import re


class LifeStageResolver:
    VERSION = '2026-09-24'
    DATE_POLICY = 'CIVIL_DATE_FEB29_ANNIVERSARY_FEB28_NO_TIMEZONE_CONVERSION'

    @staticmethod
    def civil(value):
        if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError('DATE_INVALID')
        return date.fromisoformat(value)

    @classmethod
    def age(cls, *, birth_date=None, as_of_date=None, years=None, months=None, days=None):
        if birth_date is not None:
            birth, asof = cls.civil(birth_date), cls.civil(as_of_date)
            elapsed = (asof - birth).days
            total = (asof.year-birth.year)*12 + asof.month-birth.month
            total -= asof.day < min(birth.day, monthrange(asof.year, asof.month)[1])
            precision = 'CALENDAR_DATE'
        elif days is not None:
            if type(days) is not int: raise ValueError('AGE_INVALID')
            elapsed, total, precision = days, int(days/(365.2425/12)), 'LEGACY_DAY_ESTIMATE'
        else:
            if years is None and months is None: raise ValueError('AGE_REQUIRED')
            years, months = (0 if years is None else years), (0 if months is None else months)
            if type(years) is not int or type(months) is not int or not 0 <= months < 12:
                raise ValueError('AGE_INVALID')
            total, precision = years*12 + months, 'COMPLETED_MONTHS'
            elapsed = round(total*365.2425/12)
        if not 0 <= elapsed <= 40*366 or not 0 <= total <= 40*12+11:
            raise ValueError('AGE_INVALID')
        y, m = divmod(total, 12)
        return dict(age_days=elapsed, age_years=y, age_months=m,
                    age_months_completed=total, age_years_completed=y,
                    birth_date=birth_date, as_of_date=as_of_date,
                    precision=precision, resolver_version=cls.VERSION, date_policy=cls.DATE_POLICY)

    @classmethod
    def profile_age(cls, profile):
        return cls.age(birth_date=profile.get('birth_date'), as_of_date=profile.get('as_of_date'),
                       years=profile.get('age_years'), months=profile.get('age_months'))

    @staticmethod
    def growth_context_required(species, age, profile):
        # The 24-month product default is not a universal biological maturity
        # claim. Explicit veterinary growth information always takes precedence.
        return (species == 'DOG' and not profile.get('growth_complete', False)
                and profile.get('life_stage') not in {'ADULT', 'MATURE', 'SENIOR'}
                and (profile.get('growth_complete') is False or age['age_months_completed'] < 24))

    @staticmethod
    def stage(p,store):
        import json
        from .profile import _check
        sp=p['species'];age=p['age_days'];months=p['age_months_completed']
        stages=store.keyed('life_stages','stage_id')
        params=lambda key:json.loads(stages[key]['classification_json'])
        if p.get('reproductive_status','NONE')!='NONE':return sp+'_'+p['reproductive_status'],None
        minweeks=params('DOG_EARLY_GROWTH' if sp=='DOG' else 'CAT_GROWTH')['min_age_weeks']
        if not p['weaned'] or age<minweeks*7:return sp+'_UNWEANED',None
        if sp=='CAT':
            if months<params('CAT_GROWTH')['growth_end_months']:return 'CAT_GROWTH','CAT_GROWTH'
            if p['age_years_completed']>=params('CAT_SENIOR')['min_completed_age_years']:stage='SENIOR'
            elif p['age_years_completed']>=params('CAT_MATURE')['min_age_years']:stage='MATURE'
            else:stage='ADULT'
            return 'CAT_'+stage,'CAT_ADULT_75' if p['neutered'] or p['activity']=='LOW' else 'CAT_ADULT_100'
        boundary=params('DOG_EARLY_GROWTH')['early_growth_end_weeks']*7
        if age<boundary:
            _check(not p.get('growth_complete',False),'Early-growth puppy cannot be marked growth complete')
            return 'DOG_EARLY_GROWTH','DOG_GROWTH_EARLY'
        if not p.get('growth_complete',False):
            _check('expected_adult_weight_kg' in p,'Growing dogs require expected adult weight; adult dogs require growth_complete')
            if p['expected_adult_weight_kg']<=params('DOG_LATE_GROWTH_SMALL')['adult_size_boundary_kg']:
                return 'DOG_LATE_GROWTH_SMALL','DOG_GROWTH_LATE_SMALL'
            suff='U6' if months<params('DOG_LATE_GROWTH_LARGE')['calcium_age_boundary_months'] else 'O6'
            return 'DOG_LATE_GROWTH_LARGE','DOG_GROWTH_LATE_LARGE_'+suff
        hint=p.get('life_stage_hint','ADULT');_check(hint in ['ADULT','MATURE','SENIOR'],'Invalid dog lifecycle hint')
        return 'DOG_'+hint,'DOG_ADULT_95' if p['activity']=='LOW' else 'DOG_ADULT_110'
