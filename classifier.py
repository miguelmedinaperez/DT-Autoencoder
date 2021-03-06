import numpy as np
#import matplotlib.pyplot as plt
#import pandas as pd
#from scipy.io import arff

from sklearn.metrics import recall_score, roc_auc_score

from weka.core import jvm
from weka.classifiers import Classifier, Evaluation
from weka.core.classes import Random
from weka.core.converters import Loader
from weka.filters import Filter

from copy import deepcopy
#import sklearn


def train_trees(data,attributes):

    clfs = []
    evls = []
    dt_y_hat = []

    unused_attributes = []

    for i,att in enumerate(attributes):

        data.class_index = i

        count_non_nans = np.count_nonzero(~np.isnan(data.values(i)))

        if count_non_nans<5:

            unused_attributes.append(i)
            print('Not using attribute {}, only {} real values\n\n'.format(att,count_non_nans))
            clfs.append(None)
            evls.append(None)
            dt_y_hat.append(None)
            continue

        this_clf = Classifier(classname='weka.classifiers.trees.J48',options = ['-U','-B','-M','2'])
        this_clf.build_classifier(data)

        this_evl = Evaluation(data)
        this_evl.crossvalidate_model(this_clf,data,5,Random(1))

        dt_y_hat.append(this_clf.distributions_for_instances(data))
        clfs.append(this_clf)
        evls.append(this_evl)

    return clfs,evls,dt_y_hat,unused_attributes

def get_initial_weights(data,clfs,evls,attributes,dt_y_hat,unused_attributes):
    w1_init = []
    w2_init = []

    for i,att in enumerate(attributes):
        if i in unused_attributes:
            w1_init.append(None)
            w2_init.append(None)
            continue

        print('Attribute: {}\n'.format(att))

        rocs = []

        att_values = data.attribute(i).values
        len_att_values = len(att_values)

        temp_w = np.zeros(len_att_values)

        num_nans = 0

        for j in range(len_att_values):

            this_roc = evls[i].area_under_roc(j)

            #clfs[i].distributions_for_instances(data)

            if np.isnan(this_roc):
                print('\tNAN at value {}'.format(data.attribute(i).values[j]))
                #print(clfs[i].distributions_for_instances(data))
                #exit()
                #num_nans += 1
                #this_roc = 0
            else:
                rocs.append(this_roc)

            temp = evls[i].recall(j)

            if np.isnan(temp):
                temp = 0

            temp_w[j] = temp

        if not rocs:
            rocs.append(1)

        print('\tAverage AUC: {:0.4f}\n'.format(np.mean(rocs)))

        #temp_w = temp_w+(np.random.randn(len(temp_w))*0.001)

        w1_init.append(temp_w)
        #print(w1_init)
        w2_init.append(np.mean(rocs))

    bias_init = np.zeros((len(w2_init)))

    return w2_init,w1_init,bias_init

def reLu(x):
    if x > 0:
	    return x
    return 0

def neuron_l1(x_prime,weights,bias,indxs):

    if x_prime is None:
        return None

    my_res = np.zeros((len(x_prime)))

    for i,this_x_prime in enumerate(x_prime):

        if indxs[i] >= len(weights):
            indxs[i] -= 1
        this_x_wrong = np.delete(this_x_prime,indxs[i])
        w_wrong = np.delete(weights,indxs[i])

        #my_res[i] = reLu(this_x_prime[indxs[i]]*weights[indxs[i]]-np.mean(this_x_wrong*w_wrong)+bias)
        my_res[i] = this_x_prime[indxs[i]]*weights[indxs[i]]-np.mean(this_x_wrong*w_wrong)
		
    return my_res

def get_batches(dt_y_hat,batch_size=32):

    N = len(dt_y_hat)

    if N < batch_size:
        batch_size = N

    reps = N // batch_size

    batches = []
    batch_startend = []

    for i in range(reps):
        start = i*batch_size
        end = start+batch_size
        batches.append(dt_y_hat[start:end])
        batch_startend.append([start,end])
    if end < N:
        start = end
        end = N
        batches.append(dt_y_hat[start:end])
        batch_startend.append([start,end])

    return batches,batch_startend

def train(w1_init,b1_init,lr,epochs,N,data,attributes,dt_y_hat,batch_size,unused_attributes):

    w1 = deepcopy(w1_init)
    b1 = deepcopy(b1_init)

    losses = []
    accs = []

    for epoch in range(epochs):

        hl1_this = np.zeros((N,len(dt_y_hat)))

        for j,x_prime in enumerate(dt_y_hat):
            if j in unused_attributes:
                #print(j)
                continue

            batches,batch_startend = get_batches(x_prime,batch_size=batch_size)
            num_labels = np.array(data.values(j),dtype = np.int64)

            for batch_ind, x_prime_batch in enumerate(batches):
                x_prime_prime_batch = x_prime_batch*w1[j]
                start,end = batch_startend[batch_ind]
                batch_num_labels = num_labels[start:end]

                for dani,f in enumerate(batch_num_labels):
                    if f < 0:
                        batch_num_labels[dani] = 0

                for k in np.unique(batch_num_labels):

                    if np.isnan(k):
                        k = 0

                    indices = np.where(batch_num_labels==k)
                    this_probs = x_prime_batch[indices]
                    x_prime_this = x_prime_batch[indices]
                    x_prime_prime_this = x_prime_prime_batch[indices]

                    a = neuron_l1(x_prime_this,w1[j],b1[j],np.ones((len(x_prime_this)),dtype = int)*k)

                    grad_wj = np.dot(a*(1-a),x_prime_this[:,k])
                    grad_bias = np.mean(a*(1-a))


                    w1[j][k] = w1[j][k] + lr*grad_wj
                    b1[j] = b1[j] + lr*grad_bias
                    #for this_indx in [f for f in np.arange(np.max(num_labels)) if f != k]:

                    #    if this_indx < k:
                    #        grad_indx = this_indx
                    #    elif this_indx > k:
                    #        grad_indx = this_indx-1

                    #    w1[j][this_indx] = w1[j][grad_indx] - lrw1*grad_wl[grad_indx]


        for j,x_prime in enumerate(dt_y_hat):

            num_labels = np.array(data.values(j),dtype = np.int64)

            for dani,f in enumerate(num_labels):
                if f < 0:
                    num_labels[dani] = 0

            hl1_this[:,j] = neuron_l1(x_prime,w1[j],b1[j],num_labels)

        this_loss = np.mean(hl1_this,axis = 0)
        if epoch % 10 == 0 or epoch == epochs-1:
            print('Epoch {}:'.format(epoch+1))
            for m, loss_part in enumerate(this_loss):
                print('\tAttribute {} Loss: {:0.4f}'.format(m+1,loss_part))
    return w1,b1

def test(data,N,attributes,clfs,w1,b1,w2,unused_attributes,verbose = 1):

    remove = Filter(classname='weka.filters.unsupervised.attribute.Remove',
                    options = ['-R','last'])
    remove.inputformat(data)

    data_noclass = remove.filter(data)

    dt_all = []

    for i,att in enumerate(attributes[:-1]):

        if i in unused_attributes:
            dt_all.append(None)
            continue

        data_noclass.class_index = i
        dt_all.append(clfs[i].distributions_for_instances(data_noclass))

    hl1_this_all = np.zeros((N,len(attributes[:-1])))
    preds = []

    my_div = np.zeros((N,))+len(w2)-len(unused_attributes)

    for j,x_prime in enumerate(dt_all):

        if j in unused_attributes:
            continue

        num_labels = np.array(data_noclass.values(j),dtype = np.int32)

        missing_vals = []

        doit = False
        for dani,f in enumerate(num_labels):

            if f < 0:
                doit = True
                missing_vals.append(dani)
                num_labels[dani] = 0

        if doit:
            if verbose:
                print('There were missing values on instances {} of attribute {}'.format(missing_vals,attributes[j]))

        this_preds = neuron_l1(x_prime,w1[j],b1[j],num_labels)

        for miss in missing_vals:
            this_preds[miss] = 0
            my_div[miss] -= 1
        preds.append(this_preds)

    w2_temp = np.delete(w2,unused_attributes)
    #res = np.dot(np.array(preds).T,w2_temp)/my_div
    res = np.dot(np.array(preds).T,w2_temp)

    class_index_data = data.class_index

    y = data.values(class_index_data)
    y = np.abs(y-1)
    my_score = roc_auc_score(y,res)

    return res,my_score
