import matplotlib.pyplot as plt
import seaborn as sns
from tree_titer import plot_tree, plot_dHI_distribution
import cPickle, argparse

def validation_figures(params):
	sns.set_style('darkgrid')
	virus_config.update(params.__dict__)
	# pass all these arguments to the processor: will be passed down as kwargs through all classes
	myflu = flu_process(**virus_config) 
	myflu.load()
	fig_prefix = 'figures/'+params.prefix.split('/')[-1]

	####  FIT VALIDATION  #######################################################
	myflu.map_HI_to_tree(training_fraction=params.training, method = 'nnl1reg', 
		lam_HI=params.reg, lam_pot=params.pot, lam_avi=params.avi, subset_strains = params.train_strains)
	myflu.validate(plot=True)
	plt.savefig(fig_prefix+'HI_scatter.png')

	####  effects and mutations  #######################################################
	plot_dHI_distribution(myflu.tree)
	plt.savefig(fig_prefix+'dHI_distribution.png')

	####  cHI colored tree  #######################################################
#	plot_tree(myflu.tree)
#	plt.savefig(fig_prefix+'cHI_tree.png')

	####  VIRUS EFFECTS   #######################################################
	plt.figure()
	plt.title('histogram of inferred virus effects')
	plt.hist(myflu.virus_effect.values())
	plt.xlabel('virus avidities')
	plt.savefig(fig_prefix+'HI_avidity_histogram.png')
	print "virus effects:", np.mean(myflu.virus_effect.values()), np.std(myflu.virus_effect.values())

	####  SERUM POTENCIES  #######################################################
	with open(fig_prefix+'HI_potencies.txt','w') as outfile:
		for serum, val in myflu.serum_potency.iteritems():
			outfile.write(serum[0]+'\t'+serum[1]+'\t'+str(round(val,4))+'\n')
	print "potencies:", np.mean(myflu.serum_potency.values()), np.std(myflu.serum_potency.values())

	####  DISTANCE ASYMMETRIES #######################################################
	reciprocal_measurements = []
	reciprocal_measurements_titers = []
	for (testvir, serum) in myflu.HI_normalized:
		tmp_recip = [v for v in myflu.HI_normalized if serum[0]==v[0] and testvir==v[1][0]]
		for v in tmp_recip:
			val_fwd = myflu.HI_normalized[(testvir,serum)]
			val_bwd = myflu.HI_normalized[v]
			diff_uncorrected = val_fwd - val_bwd
			diff_corrected = (val_fwd - myflu.serum_potency[serum] - myflu.virus_effect[testvir])\
							-(val_bwd - myflu.serum_potency[v[1]] - myflu.virus_effect[serum[0]])
			val_bwd = myflu.HI_normalized[v]
			reciprocal_measurements.append([testvir, serum, diff_uncorrected, diff_corrected])
			reciprocal_measurements_titers.append([testvir, serum, val_fwd, val_bwd, 
			                                      (val_fwd - myflu.serum_potency[serum] - myflu.virus_effect[testvir]),
                      							  (val_bwd - myflu.serum_potency[v[1]] - myflu.virus_effect[serum[0]]),
												  ])

	plt.figure()
	plt.title('asymmetry in reciprocal titers')
	plt.hist([x[2] for x in reciprocal_measurements],alpha=0.7, label="uncorrected", normed=True)
	plt.hist([x[3] for x in reciprocal_measurements],alpha=0.7, label="corrected", normed=True)
	plt.xlabel('distance asymmetry')
	plt.legend()
	plt.savefig(fig_prefix+'HI_titer_asymmetry.png')

	####  Analyze all cliques #######################################################
	all_reciprocal = list(set([v[1] for v in reciprocal_measurements_titers]))

	import networkx as nx
	from random import sample
	G = nx.Graph()
	G.add_nodes_from(all_reciprocal)
	for vi,v in enumerate(all_reciprocal):
		for w in all_reciprocal[:vi]:
			if ((v[0], w) in myflu.HI_normalized) and ((w[0], v) in myflu.HI_normalized):
				G.add_edge(v,w)
	print "generated graph"
	C = nx.find_cliques(G)
	print "found cliques"
	def symm_distance(v,w):
		res =  myflu.HI_normalized[(v[0], w)] - myflu.virus_effect[v[0]] - myflu.serum_potency[w]
		res += myflu.HI_normalized[(w[0], v)] - myflu.virus_effect[w[0]] - myflu.serum_potency[v]
		return res*0.5

	additivity_test = {'test':[], 'control':[]}
	n_quartets = 1000
	for clique in C:
		if len(clique)>8:
			for i in xrange(n_quartets):
				Q = sample(clique, 4)
				dists = []
				for (a,b) in [((0,1), (2,3)),((0,2), (1,3)), ((0,3), (1,2))]:
					dists.append(symm_distance(Q[a[0]], Q[a[1]])+symm_distance(Q[b[0]], Q[b[1]]))
				dists.sort(reverse=True)
				additivity_test['test'].append(dists[0]-dists[1])

				dists = []
				for di in range(3):
					a,b,c,d = sample(clique,4)
					dists.append(symm_distance(a, b)+symm_distance(c,d))
				dists.sort(reverse=True)
				additivity_test['control'].append(dists[0]-dists[1])

	plt.figure()
	plt.title('deviations from tree additivity')
	plt.hist(additivity_test['control'], alpha=0.7,normed=True, bins = np.linspace(0,3,18))
	plt.hist(additivity_test['test'], alpha=0.7,normed=True, bins = np.linspace(0,3,18))
	plt.xlabel('deviation')
	plt.legend()
	plt.savefig(fig_prefix+'HI_titer_tree_additivity.png')

	#### titer effects ###############################################################
	dHI_list = []
	for node in myflu.tree.postorder_node_iter():
		dHI_list.append((node.dHI, node.mutations, node))
	dHI_list.sort()
	return dHI_list, myflu

def scan_regularization(params, grid):
	virus_config.update(params.__dict__)
	# pass all these arguments to the processor: will be passed down as kwargs through all classes
	myH3N2 = flu_process(**virus_config) 
	myflu.load()
	fig_prefix = 'figures/'+params.prefix.split('/')[-1]

	####  looping over different combinations of regularizers  ########################
	accuracy = np.zeros((len(grid), len(grid), len(grid), 5))
	for hi, lam_HI in enumerate(grid):
		for pi, lam_pot in enumerate(grid):
			for ai, lam_avi in enumerate(grid):
				myflu.map_HI_to_tree(training_fraction=params.training, method = 'nnl1reg', 
				lam_HI=lam_HI, lam_pot=lam_pot, lam_avi=lam_avi, subset_strains = params.train_strains)
				myflu.validate(plot=False)
				####  calculated asymmetries 
				reciprocal_measurements = []
				for (testvir, serum) in myflu.HI_normalized:
					tmp_recip = [v for v in myflu.HI_normalized if serum[0]==v[0] and testvir==v[1][0]]
					for v in tmp_recip:
						val_fwd = myflu.HI_normalized[(testvir,serum)]
						val_bwd = myflu.HI_normalized[v]
						diff_uncorrected = val_fwd - val_bwd
						diff_corrected = (val_fwd - myflu.serum_potency[serum] - myflu.virus_effect[testvir])\
										-(val_bwd - myflu.serum_potency[v[1]] - myflu.virus_effect[serum[0]])
						reciprocal_measurements.append([testvir, serum, diff_uncorrected, diff_corrected])
				accuracy[hi,pi, ai]=myflu.rms_error, myflu.abs_error, myflu.slope, myflu.intercept, np.std([x[3] for x in reciprocal_measurements])
				print lam_HI, lam_pot, lam_avi, accuracy[hi,pi,ai]

	return accuracy

if __name__=="__main__":
	plt.ion()
	parser = argparse.ArgumentParser(description='Process virus sequences, build tree, and prepare of web visualization')
	parser.add_argument('--prefix', type = str, default = 'data/', help='path+prefix of file dumps')
	parser.add_argument('--flutype', type = str, default = 'H3N2', help='flu strain')
	parser.add_argument('--training', type = float, default = 0.8, help='fraction of data used for training')
	parser.add_argument('--train_strains', default = False, action = 'store_true', help='subset measurements or strains to train')
	parser.add_argument('--reg', type = float, default = 1.0, help='regularization parameter')
	parser.add_argument('--avi', type = float, default = 1.0, help='regularization parameter')
	parser.add_argument('--pot', type = float, default = 1.0, help='regularization parameter')
	parser.add_argument('--resolution', type = str,  help ="label for the resolution")	
	parser.add_argument('--min_aamuts', type = str, default = '0', help='minimal number of aminoacid mutations to include branch or epi for epitope or rbs for receptor binding site')
	params = parser.parse_args()
	if params.flutype=='H3N2':
		from H3N2_process import *
		flu_process = H3N2_process
	elif params.flutype=='H1N1pdm':
		from H1N1pdm_process import *
		flu_process = H1N1pdm_process
	elif params.flutype=='H1N1':
		from H1N1_process import *
		flu_process = H1N1_process
	elif params.flutype=='Vic':
		from Vic_process import *
		flu_process = BVic_process
	elif params.flutype=='Yam':
		from Yam_process import *
		flu_process = BYam_process
	try:
		params.min_aamuts = int(params.min_aamuts)
	except:
		pass
	params.__dict__['HI_fname']='source-data/'+params.flutype+'_HI_titers.txt'	

	dHI_list,myflu = validation_figures(params)
	#grid = [0.1, 0.3, 1, 3, 10]
	#accuracy = scan_regularization(params, grid)
#
#	#for ii in range(accuracy.shape[-1]):
#	#	plt.figure()
#	#	for hi, lam_HI in enumerate(grid):
#	#		plt.subplot(len(grid)//2+len(grid)%2, 2, hi+1)
#	#		plt.title('lam_HI='+str(lam_HI))
	#		plt.imshow(accuracy[hi,:,:,ii], interpolation='nearest')

