"""Evidence applicability and provenance; missing data is never invented."""
ROLE_SOURCE = {
    'source_id':'MSD_NUTRITION2024', 'organization':'MSD Veterinary Manual',
    'document':'Nutritional Requirements of Small Animals', 'year':2024,
    'version':'Updated September 2024', 'basis':'PHYSIOLOGIC_ROLE_NOT_DOSAGE',
    'url':'https://www.msdvetmanual.com/management-and-nutrition/nutrition-small-animals/nutritional-requirements-of-small-animals',
    'read_status':'RELEVANT_SECTIONS_READ', 'evidence_status':'VERIFIED',
}
ROLES = {
 'CALCIUM':'维持骨骼和牙齿正常结构、神经肌肉功能及钙磷平衡。',
 'TAURINE':'支持猫的视网膜和心肌正常功能，并参与胆汁酸结合。',
 'OMEGA3_EPA_DHA':'提供长链 Omega-3，参与细胞膜和正常炎症调节；具体意义取决于生命阶段和已有营养要求。',
 'VITAMIN_MINERAL':'帮助满足代谢、酶功能和组织维持所需的维生素与矿物质；补足家庭食材难以稳定覆盖的微量营养。',
}
LABELS = {
 'CALCIUM':['每份元素钙含量（mg），不是钙盐总重量','每份的克数/毫升数；同时列明磷和其他活性成分'],
 'TAURINE':['每克或每份有效牛磺酸含量（mg）','适用物种与生命阶段、每份定义和其他成分'],
 'OMEGA3_EPA_DHA':['每份 EPA 和 DHA 各自含量（mg）或明确的合计','每粒/每mL的定义、总油脂和能量；不能用鱼油总重替代 EPA+DHA'],
 'VITAMIN_MINERAL':['犬/猫与生命阶段适用性','每份维生素 A/D/E、B 族及锌/铜/锰/碘/硒等实际含量与单位','完整成分表、每份定义和钙磷；不要叠加重复营养来源'],
}

def source_record(store, sid, basis=None, locator=None):
    if sid == ROLE_SOURCE['source_id']:
        return {**ROLE_SOURCE, 'basis':basis or ROLE_SOURCE['basis'], 'locator':locator}
    row=store.keyed('sources','source_id').get(sid)
    if row is None:
        return {'source_id':sid,'organization':None,'document':None,'year':None,'version':None,
                'basis':basis,'locator':locator,'evidence_status':'NEEDS_EVIDENCE'}
    numeric_read=row['read_status'] in {'RELEVANT_SECTIONS_READ','FULL_RELEVANT_SECTIONS_READ','READ'}
    complete=all(row.get(k) is not None for k in ('organization','title','year','version'))
    return {'source_id':sid,'organization':row['organization'],'document':row['title'],
            'year':row['year'],'version':row['version'],'basis':basis,'locator':locator,
            'url':row['URL'],'read_status':row['read_status'],
            'evidence_status':'VERIFIED' if complete and numeric_read else 'NEEDS_EVIDENCE',
            'limitation':None if complete and numeric_read else '来源元数据或已阅读全文范围不足，不推定定量依据。'}


def quality_indicators(store, kind):
    result=[{'indicator':r['quality_category'],'what_it_checks':r['scope'],
             'limitation':r['limitations'],'source_id':r['source_id'],'required':False}
            for r in store.rows('supplement_quality_guides')]
    result += [{'indicator':'BATCH_ACTIVE_CONTENT','what_it_checks':'对应产品和批次的有效成分、污染物检测及报告可追溯性',
                'limitation':'体系认证不能代替成品/批次含量；不同证据不按国家或证书简单排名。','source_id':'USI_POLICY','required':False}]
    if kind=='OMEGA3_EPA_DHA':
        result += [{'indicator':'OIL_OXIDATION','what_it_checks':'鱼油批次氧化和污染物检测，报告需说明方法与适用标准',
                    'limitation':'未在此设定未经核验的通用合格数值。','source_id':'USI_POLICY','required':False}]
    return result
